import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** Tailwind-aware className merge. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}

export const clamp = (v: number, min: number, max: number): number =>
  Math.min(max, Math.max(min, v))

export const lerp = (a: number, b: number, t: number): number => a + (b - a) * t

export const uid = (): string => Math.random().toString(36).slice(2, 10)

/** Promise-based delay for the orchestration conductor. */
export const wait = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms))
