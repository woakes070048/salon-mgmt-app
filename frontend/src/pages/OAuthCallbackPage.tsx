import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { setToken } from '@/api/client'
import { getMe } from '@/api/auth'
import { useAuth } from '@/store/auth'

export default function OAuthCallbackPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const { setUser } = useAuth()

  useEffect(() => {
    const token = params.get('token')
    const error = params.get('error')

    if (error || !token) {
      navigate(`/login?error=${error ?? 'unknown'}`, { replace: true })
      return
    }

    setToken(token)
    getMe()
      .then(user => {
        setUser(user)
        navigate(user.role === 'guest' ? '/my-requests' : '/dashboard', { replace: true })
      })
      .catch(() => navigate('/login?error=auth_failed', { replace: true }))
  }, [])

  return <div className="min-h-screen bg-muted/30" />
}
