import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/** ترکیب کلاس‌ها با حل تعارض Tailwind. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
