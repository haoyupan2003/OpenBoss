const base = import.meta.env.VITE_API_BASE || ''
export function apiUrl(path: string): string { return base + path }
