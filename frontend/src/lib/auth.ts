export const auth = {
  getToken: (): string | null => localStorage.getItem('token'),
  setToken: (token: string): void => localStorage.setItem('token', token),
  removeToken: (): void => localStorage.removeItem('token'),
  isLoggedIn: (): boolean => !!localStorage.getItem('token'),
}
