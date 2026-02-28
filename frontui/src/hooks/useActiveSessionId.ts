import { useEffect, useState } from 'react'
import { getActiveSessionId, SESSION_CHANGED_EVENT } from '../lib/session'

export function useActiveSessionId(): string {
  const [id, setId] = useState<string>(() => getActiveSessionId() ?? 'repo')

  useEffect(() => {
    const sync = () => setId(getActiveSessionId() ?? 'repo')
    window.addEventListener(SESSION_CHANGED_EVENT, sync)
    window.addEventListener('storage', sync)
    return () => {
      window.removeEventListener(SESSION_CHANGED_EVENT, sync)
      window.removeEventListener('storage', sync)
    }
  }, [])

  return id
}
