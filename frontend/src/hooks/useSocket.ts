import { useEffect, useRef } from 'react'
import { getSocket } from '@/lib/socket'

export function useSocket(event: string, handler: (data: unknown) => void) {
  const handlerRef = useRef(handler)
  handlerRef.current = handler

  useEffect(() => {
    const socket = getSocket()
    const fn = (data: unknown) => handlerRef.current(data)
    socket.on(event, fn)
    return () => {
      socket.off(event, fn)
    }
  }, [event])
}
