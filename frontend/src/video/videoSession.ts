import { createContext, useContext } from 'react'

export type FeedStatus = 'idle' | 'connecting' | 'live' | 'recording' | 'error'

export interface VideoSessionValue {
  stream: MediaStream | null
  status: FeedStatus
}

export const VideoSessionContext = createContext<VideoSessionValue>({ stream: null, status: 'idle' })

/** Access the shared spectator stream + status (provided by VideoSessionProvider). */
export function useVideoSession(): VideoSessionValue {
  return useContext(VideoSessionContext)
}
