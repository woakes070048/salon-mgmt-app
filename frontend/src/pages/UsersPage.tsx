import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MailIcon, PlusIcon, ShieldCheckIcon, Trash2Icon, UserIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import {
  type AdminUser,
  createUser,
  deleteUser,
  listUsers,
  sendResetLink,
  sendWelcomeEmail,
  updateUser,
} from '@/api/admin'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const ROLE_VARIANT: Record<string, 'default' | 'secondary' | 'outline'> = {
  super_admin: 'default',
  tenant_admin: 'default',
  staff: 'secondary',
  guest: 'outline',
}

function RoleBadge({ role }: { role: string }) {
  const { t } = useTranslation()
  const ROLE_LABEL: Record<string, string> = {
    super_admin: t('users.role_super_admin'),
    tenant_admin: t('users.role_admin_label'),
    staff: t('users.role_staff_label'),
    guest: t('users.role_guest'),
  }
  return (
    <Badge variant={ROLE_VARIANT[role] ?? 'outline'}>
      {ROLE_LABEL[role] ?? role}
    </Badge>
  )
}

// ── New user dialog ───────────────────────────────────────────────────────────

function NewUserDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [email, setEmail] = useState('')
  const [role, setRole] = useState('staff')
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () => createUser({
      email: email.trim(),
      role,
      send_welcome: true,
      first_name: firstName.trim() || null,
      last_name: lastName.trim() || null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-users'] })
      setEmail('')
      setRole('staff')
      setFirstName('')
      setLastName('')
      setError(null)
      onClose()
    },
    onError: (err: unknown) => {
      setError((err as Error).message ?? t('common.error_generic'))
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    mutation.mutate()
  }

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) onClose() }}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{t('users.add_user_title')}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 pt-2">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="first-name">{t('auth.first_name')}</Label>
              <Input
                id="first-name"
                value={firstName}
                onChange={e => setFirstName(e.target.value)}
                placeholder="Optional"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="last-name">{t('auth.last_name')}</Label>
              <Input
                id="last-name"
                value={lastName}
                onChange={e => setLastName(e.target.value)}
                placeholder="Optional"
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="email">{t('common.email')}</Label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="name@example.com"
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="role">{t('common.type')}</Label>
            <Select value={role} onValueChange={v => { if (v) setRole(v) }}>
              <SelectTrigger id="role">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="staff">{t('users.role_staff')}</SelectItem>
                <SelectItem value="tenant_admin">{t('users.role_admin')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <p className="text-xs text-muted-foreground">
            {t('users.welcome_email_help')}
          </p>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? t('common.sending') : t('users.create_send_welcome')}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// ── Edit role dialog ──────────────────────────────────────────────────────────

function EditUserDialog({
  user,
  onClose,
}: {
  user: AdminUser
  onClose: () => void
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [role, setRole] = useState(user.role)
  const [firstName, setFirstName] = useState(user.first_name ?? '')
  const [lastName, setLastName] = useState(user.last_name ?? '')
  const [langPref, setLangPref] = useState(user.language_preference ?? 'en')
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () => updateUser(user.id, {
      role,
      first_name: firstName.trim() || null,
      last_name: lastName.trim() || null,
      language_preference: langPref,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-users'] })
      onClose()
    },
    onError: (err: unknown) => {
      setError((err as Error).message ?? t('common.error_generic'))
    },
  })

  const isDirty = role !== user.role
    || firstName.trim() !== (user.first_name ?? '')
    || lastName.trim() !== (user.last_name ?? '')
    || langPref !== (user.language_preference ?? 'en')

  return (
    <Dialog open onOpenChange={v => { if (!v) onClose() }}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{t('users.edit_user_title')}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 pt-2">
          <p className="text-xs text-muted-foreground">{user.email}</p>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>{t('auth.first_name')}</Label>
              <Input value={firstName} onChange={e => setFirstName(e.target.value)} placeholder="Optional" />
            </div>
            <div className="space-y-1.5">
              <Label>{t('auth.last_name')}</Label>
              <Input value={lastName} onChange={e => setLastName(e.target.value)} placeholder="Optional" />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>{t('common.type')}</Label>
            <Select value={role} onValueChange={v => { if (v) setRole(v as AdminUser['role']) }}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="staff">{t('users.role_staff')}</SelectItem>
                <SelectItem value="tenant_admin">{t('users.role_admin')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>{t('users.language_preference')}</Label>
            <select
              value={langPref}
              onChange={e => setLangPref(e.target.value)}
              className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background"
            >
              <option value="en">{t('translations.lang_en')}</option>
              <option value="fr">{t('translations.lang_fr')}</option>
            </select>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
            <Button onClick={() => mutation.mutate()} disabled={mutation.isPending || !isDirty}>
              {t('common.save')}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ── User row ──────────────────────────────────────────────────────────────────

function UserRow({ user }: { user: AdminUser }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [editOpen, setEditOpen] = useState(false)
  const [confirmDeactivate, setConfirmDeactivate] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const welcomeMutation = useMutation({
    mutationFn: () => sendWelcomeEmail(user.id),
    onError: (err: unknown) => {
      setActionError((err as Error).message ?? 'Failed to send email')
    },
  })

  const resetMutation = useMutation({
    mutationFn: () => sendResetLink(user.id),
    onError: (err: unknown) => {
      setActionError((err as Error).message ?? 'Failed to send email')
    },
  })

  const toggleMutation = useMutation({
    mutationFn: () => updateUser(user.id, { is_active: !user.is_active }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-users'] })
      setConfirmDeactivate(false)
    },
    onError: (err: unknown) => {
      setActionError((err as Error).message ?? t('common.error_generic'))
    },
  })

  const [confirmDelete, setConfirmDelete] = useState(false)

  const deleteMutation = useMutation({
    mutationFn: () => deleteUser(user.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-users'] }); setConfirmDelete(false) },
    onError: (err: unknown) => { setActionError((err as Error).message ?? 'Delete failed'); setConfirmDelete(false) },
  })

  const isGuest = user.role === 'guest'

  return (
    <>
      <tr className={`border-b last:border-0 ${!user.is_active ? 'opacity-50' : ''}`}>
        <td className="px-4 py-3">
          <div className="flex items-center gap-2">
            {user.role === 'tenant_admin' || user.role === 'super_admin'
              ? <ShieldCheckIcon size={14} className="text-muted-foreground flex-shrink-0" />
              : <UserIcon size={14} className="text-muted-foreground flex-shrink-0" />
            }
            <div>
              <p className="text-sm font-medium">{user.email}</p>
              {(user.first_name || user.last_name) ? (
                <p className="text-xs text-muted-foreground">
                  {[user.first_name, user.last_name].filter(Boolean).join(' ')}
                </p>
              ) : user.client_name ? (
                <p className="text-xs text-muted-foreground">{user.client_name}</p>
              ) : null}
            </div>
          </div>
        </td>
        <td className="px-4 py-3">
          <RoleBadge role={user.role} />
        </td>
        <td className="px-4 py-3">
          <span className={`text-xs font-medium ${user.is_active ? 'text-green-600' : 'text-muted-foreground'}`}>
            {user.is_active ? t('users.status_active') : t('users.status_inactive')}
          </span>
        </td>
        <td className="px-4 py-3 text-right">
          {actionError && (
            <span className="text-xs text-destructive mr-2">{actionError}</span>
          )}
          <div className="flex items-center justify-end gap-1">
            {!isGuest && (
              <Button
                size="sm"
                variant="ghost"
                className="text-xs h-7"
                onClick={() => setEditOpen(true)}
              >
                {t('users.action_edit')}
              </Button>
            )}
            {!isGuest && (
              <Button
                size="sm"
                variant="ghost"
                className="text-xs h-7"
                disabled={welcomeMutation.isPending}
                onClick={() => { setActionError(null); welcomeMutation.mutate() }}
                title="Send welcome / password setup email"
              >
                <MailIcon size={13} className="mr-1" />
                {welcomeMutation.isPending ? t('common.sending') : welcomeMutation.isSuccess ? t('users.sent_confirm') : t('users.send_welcome')}
              </Button>
            )}
            {!isGuest && (
              <Button
                size="sm"
                variant="ghost"
                className="text-xs h-7 text-muted-foreground"
                disabled={resetMutation.isPending}
                onClick={() => { setActionError(null); resetMutation.mutate() }}
                title="Send password reset link"
              >
                {resetMutation.isPending ? t('common.sending') : resetMutation.isSuccess ? t('users.send_reset_confirm') : t('users.send_reset')}
              </Button>
            )}
            {!isGuest && !confirmDeactivate && (
              <Button
                size="sm"
                variant="ghost"
                className="text-xs h-7 text-muted-foreground"
                onClick={() => setConfirmDeactivate(true)}
              >
                {user.is_active ? t('users.action_deactivate') : t('users.action_reactivate')}
              </Button>
            )}
            {confirmDeactivate && (
              <span className="flex items-center gap-1">
                <span className="text-xs text-muted-foreground">{t('common.sure')}</span>
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-xs h-7 text-destructive"
                  disabled={toggleMutation.isPending}
                  onClick={() => toggleMutation.mutate()}
                >
                  {t('common.yes')}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-xs h-7"
                  onClick={() => setConfirmDeactivate(false)}
                >
                  {t('common.no')}
                </Button>
              </span>
            )}
            {!confirmDelete && (
              <Button
                size="sm"
                variant="ghost"
                className="text-xs h-7 text-muted-foreground"
                onClick={() => { setConfirmDelete(true); setConfirmDeactivate(false); setActionError(null) }}
                title="Permanently delete user"
              >
                <Trash2Icon size={13} />
              </Button>
            )}
            {confirmDelete && (
              <span className="flex items-center gap-1 flex-wrap justify-end">
                <span className="text-xs text-muted-foreground">
                  {t('users.confirm_delete')}
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-xs h-7 text-destructive"
                  disabled={deleteMutation.isPending}
                  onClick={() => deleteMutation.mutate()}
                >
                  {deleteMutation.isPending ? t('users.deleting') : t('users.action_delete')}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-xs h-7"
                  onClick={() => setConfirmDelete(false)}
                >
                  {t('common.cancel')}
                </Button>
              </span>
            )}
          </div>
        </td>
      </tr>
      {editOpen && <EditUserDialog user={user} onClose={() => setEditOpen(false)} />}
    </>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function UsersPage() {
  const { t } = useTranslation()
  const [newOpen, setNewOpen] = useState(false)

  const { data: users = [], isLoading } = useQuery({
    queryKey: ['admin-users'],
    queryFn: listUsers,
  })

  const staffAndAdmin = users.filter(u => u.role !== 'guest')
  const guests = users.filter(u => u.role === 'guest')

  return (
    <div className="h-full overflow-auto bg-muted/30">
      <div className="max-w-4xl mx-auto px-6 py-8 space-y-6">

        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold">{t('users.page_title')}</h1>
            <p className="text-muted-foreground text-sm mt-0.5">
              {t('users.page_subtitle')}
            </p>
          </div>
          <Button onClick={() => setNewOpen(true)}>
            <PlusIcon size={14} className="mr-1.5" />
            {t('users.add_user')}
          </Button>
        </div>

        {isLoading ? (
          <div className="bg-white border rounded-lg p-8 text-center text-sm text-muted-foreground">
            {t('common.loading')}
          </div>
        ) : (
          <>
            <div className="bg-white border rounded-lg overflow-hidden">
              <div className="px-4 py-3 border-b">
                <h2 className="text-sm font-medium">{t('users.staff_admins_section')}</h2>
              </div>
              {staffAndAdmin.length === 0 ? (
                <p className="text-sm text-muted-foreground px-4 py-6 text-center">{t('users.no_users')}</p>
              ) : (
                <table className="w-full">
                  <thead>
                    <tr className="border-b bg-muted/30">
                      <th className="text-left px-4 py-2 text-xs font-medium text-muted-foreground">{t('users.col_user')}</th>
                      <th className="text-left px-4 py-2 text-xs font-medium text-muted-foreground">{t('users.col_role')}</th>
                      <th className="text-left px-4 py-2 text-xs font-medium text-muted-foreground">{t('users.col_status')}</th>
                      <th className="px-4 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {staffAndAdmin.map(u => <UserRow key={u.id} user={u} />)}
                  </tbody>
                </table>
              )}
            </div>

            {guests.length > 0 && (
              <div className="bg-white border rounded-lg overflow-hidden">
                <div className="px-4 py-3 border-b">
                  <h2 className="text-sm font-medium">{t('users.guest_section')}</h2>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {t('users.guest_help')}
                  </p>
                </div>
                <table className="w-full">
                  <thead>
                    <tr className="border-b bg-muted/30">
                      <th className="text-left px-4 py-2 text-xs font-medium text-muted-foreground">{t('users.col_user')}</th>
                      <th className="text-left px-4 py-2 text-xs font-medium text-muted-foreground">{t('users.col_role')}</th>
                      <th className="text-left px-4 py-2 text-xs font-medium text-muted-foreground">{t('users.col_status')}</th>
                      <th className="px-4 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {guests.map(u => <UserRow key={u.id} user={u} />)}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>

      <NewUserDialog open={newOpen} onClose={() => setNewOpen(false)} />
    </div>
  )
}
