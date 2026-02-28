import { useEffect, useRef } from 'react'

export function useInterval(cb: () => void, delayMs: number | null): void {
  const cbRef = useRef(cb)
  cbRef.current = cb

  useEffect(() => {
    if (delayMs === null) return
    const id = window.setInterval(() => cbRef.current(), delayMs)
    return () => window.clearInterval(id)
  }, [delayMs])
}
