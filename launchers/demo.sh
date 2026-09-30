#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT" || exit 1

# By default the network starts empty: people join with any name, create their own room, and other
# nodes join that room. Pass --demo-peers for the scripted cast (Alice, Bob, Mallory and swarm
# peers in room "demo").
profile_args=()
if [[ "${1:-}" == "--demo-peers" ]]; then
  profile_args=(--profile demo)
else
  # Leftover demo peers from an earlier run would still be sitting in room "demo".
  docker compose --profile demo rm -sf peer-alice peer-bob peer-mallory peer-swarm >/dev/null 2>&1 || true
fi

compose_args=(${profile_args[@]+"${profile_args[@]}"} up -d --build --wait --wait-timeout 90)
compose_output=$(docker compose "${compose_args[@]}" 2>&1)
compose_status=$?
if (( compose_status != 0 )) \
  && printf '%s\n' "$compose_output" | grep -Eqi 'failed to fetch anonymous token' \
  && printf '%s\n' "$compose_output" | grep -Eqi 'auth\.docker\.io|registry-1\.docker\.io' \
  && printf '%s\n' "$compose_output" | grep -Eqi 'i/o timeout|no such host|temporary failure in name resolution|connection timed out'; then
  printf '\033[33mDocker Hub DNS/token request timed out. Retrying Compose startup once...\033[0m\n' >&2
  printf '%s\n' "$compose_output" \
    | grep -Ei 'failed to fetch anonymous token|auth\.docker\.io|registry-1\.docker\.io|lookup .* (i/o timeout|no such host|temporary failure)|connection timed out' >&2 || true
  sleep 3
  retry_output=$(docker compose "${compose_args[@]}" 2>&1)
  retry_status=$?
  compose_output+=$'\n\n--- Docker Compose retry output ---\n'"$retry_output"
  compose_status=$retry_status
  if (( compose_status == 0 )); then
    printf '\033[32mDocker Compose startup succeeded on retry.\033[0m\n'
  fi
fi

if (( compose_status != 0 )); then
  printf '\033[31mERROR: Docker Compose failed to start the application (exit code %s).\033[0m\n' "$compose_status" >&2
  printf '%s\n' "$compose_output" >&2
  printf '\033[33mDocker Compose service status:\033[0m\n' >&2
  docker compose ps -a >&2 || true
  printf '\033[33mRecent cloudflared logs:\033[0m\n' >&2
  docker compose logs --no-color --tail=100 cloudflared >&2 || true
  exit "$compose_status"
fi

printf '\033[36mDocker Compose started. Waiting up to 90 seconds for the Cloudflare Quick Tunnel URL...\033[0m\n'
deadline=$((SECONDS + 90))
public_url=""

while (( SECONDS < deadline )); do
  cloudflared_logs=$(docker compose logs --no-color --tail=200 cloudflared 2>&1)
  logs_status=$?
  if (( logs_status == 0 )); then
    public_url=$(printf '%s\n' "$cloudflared_logs" \
      | grep -Eo 'https?://[[:alnum:]]([[:alnum:]-]*[[:alnum:]])?\.trycloudflare\.com' \
      | tail -n 1 || true)
    if [[ -n "$public_url" ]]; then
      break
    fi
  fi
  sleep 2
done

if [[ -z "$public_url" ]]; then
  printf '\033[31mERROR: No trycloudflare.com URL was detected within 90 seconds.\033[0m\n' >&2
  printf '\033[33mDocker Compose service status:\033[0m\n' >&2
  docker compose ps -a >&2
  printf '\033[33mRecent cloudflared logs:\033[0m\n' >&2
  docker compose logs --no-color --tail=100 cloudflared 2>&1 >&2
  exit 1
fi

clipboard_message=""
if command -v wl-copy >/dev/null 2>&1; then
  if printf '%s' "$public_url" | wl-copy; then
    clipboard_message="URL copied to clipboard."
  fi
elif command -v xclip >/dev/null 2>&1; then
  if printf '%s' "$public_url" | xclip -selection clipboard; then
    clipboard_message="URL copied to clipboard."
  fi
elif command -v xsel >/dev/null 2>&1; then
  if printf '%s' "$public_url" | xsel --clipboard --input; then
    clipboard_message="URL copied to clipboard."
  fi
fi

if [[ -z "$clipboard_message" ]]; then
  clipboard_message="Clipboard utility unavailable; copy the URL above manually. Install wl-clipboard, xclip, or xsel to enable clipboard copying."
fi

printf '\n\033[32m================================================\n'
printf '                 DEMO LIVE\n'
printf '================================================\033[0m\n'
printf '\033[33mPUBLIC DEMO URL\033[0m\n'
printf '%s\n' "$public_url"
if [[ "$clipboard_message" == "URL copied to clipboard." ]]; then
  printf '\033[90m(Also copied to clipboard.)\033[0m\n'
fi
printf '\033[32m================================================\033[0m\n'
printf "Following Docker Compose logs. Press Ctrl+C to detach; containers will keep running.\n"
docker compose ${profile_args[@]+"${profile_args[@]}"} logs --follow --tail=20
printf "Detached from Compose logs. Docker containers remain running.\n"
