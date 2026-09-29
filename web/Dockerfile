FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./
# npm ci refuses to run here: the committed lockfile was generated on a
# Windows/Mac dev machine, and npm's optional-dependency resolution for
# native packages (lightningcss, @tailwindcss/oxide) prunes entries for
# platforms it wasn't run on - so it's missing the alpine/musl-specific
# @emnapi/core+@emnapi/runtime WASM-fallback entries this image needs.
# Regenerating the lockfile from inside this same image fixes the Docker
# build but drops the Windows/Mac-only entries in exchange, breaking
# `npm ci`/`npm install` for teammates developing locally on those
# platforms - not worth that tradeoff for a dev-mode container. npm
# install (not ci) resolves whatever this specific platform needs at
# build time regardless of what's in the lockfile.
RUN npm install

COPY . .

EXPOSE 8080

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "8080"]
