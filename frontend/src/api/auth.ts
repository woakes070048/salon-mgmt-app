import { api, setToken } from './client'

export interface MeResponse {
  id: string
  email: string
  role: 'super_admin' | 'tenant_admin' | 'staff' | 'guest'
  tenant_id: string
  language_preference: string
  display_name: string | null
  provider_id: string | null
}

export async function login(email: string, password: string): Promise<MeResponse> {
  const { access_token } = await api.post<{ access_token: string }>('/auth/login', {
    email,
    password,
  })
  setToken(access_token)
  return api.get<MeResponse>('/auth/me')
}

export async function register(
  first_name: string,
  last_name: string,
  email: string,
  phone: string,
  password: string,
  language_preference = 'en',
): Promise<MeResponse> {
  const { access_token } = await api.post<{ access_token: string }>('/auth/register', {
    first_name,
    last_name,
    email,
    phone,
    password,
    language_preference,
  })
  setToken(access_token)
  return api.get<MeResponse>('/auth/me')
}

export function getMe(): Promise<MeResponse> {
  return api.get<MeResponse>('/auth/me')
}

export function requestReset(email: string): Promise<void> {
  return api.post<void>('/auth/request-reset', { email })
}

export function resetPassword(token: string, password: string): Promise<void> {
  return api.post<void>('/auth/reset-password', { token, password })
}

export function updateLanguagePreference(language_preference: string): Promise<MeResponse> {
  return api.patch<MeResponse>('/auth/me', { language_preference })
}

export function changePassword(current_password: string, new_password: string): Promise<void> {
  return api.post<void>('/auth/change-password', { current_password, new_password })
}
