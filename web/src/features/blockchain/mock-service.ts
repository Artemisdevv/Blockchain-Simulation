import {
  initialMockData,
  type MempoolResponse,
  type StakeResponse,
  type StakersResponse,
  type TransactionResponse,
} from "./mock-data";

export const createMockState = () => structuredClone(initialMockData);

export function submitMockTransaction(
  mempool: MempoolResponse,
  receiver: string,
  amount: number,
): { response: TransactionResponse; mempool: MempoolResponse } {
  const id = `tx-${crypto.randomUUID()}`;
  return {
    response: { ok: true, transaction_id: id },
    mempool: {
      transactions: [
        {
          id,
          payload: amount,
          sender: initialMockData.balance.public_key,
          receiver,
          ts: Date.now() / 1000,
        },
        ...mempool.transactions,
      ],
    },
  };
}

export function submitMockStake(
  stakers: StakersResponse,
  amount: number,
  balance: number,
): { response: StakeResponse; stakers: StakersResponse } {
  if (amount > balance)
    return { response: { ok: false, error: "Insufficient balance for this stake." }, stakers };
  return {
    response: { ok: true, creating_block_in_seconds: stakers.epoch_ends_in_seconds },
    stakers: {
      ...stakers,
      stakers: { ...stakers.stakers, [initialMockData.balance.public_key]: amount },
    },
  };
}
