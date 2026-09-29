const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

async function request(path, options = {}) {
  let response

  try {
    response = await fetch(`${API_BASE_URL}${path}`, options)
  } catch {
    throw new Error('VideoMind could not reach the backend. Make sure the API is running and try again.')
  }

  let data = null
  try {
    data = await response.json()
  } catch {
    // The response may not contain JSON, so use the HTTP status below.
  }

  if (!response.ok) {
    const detail = typeof data?.detail === 'string' ? data.detail : ''
    throw new Error(detail || `The backend returned an error (${response.status}).`)
  }

  return data
}

export function createYouTubeVideo(url) {
  return request(`/videos/youtube?url=${encodeURIComponent(url)}`, { method: 'POST' })
}

export function uploadVideo(file) {
  const formData = new FormData()
  formData.append('file', file)
  return request('/videos/upload', { method: 'POST', body: formData })
}

export function startVideoAnalysis(videoId) {
  return request(`/videos/${videoId}/analyze`, { method: 'POST' })
}

export function getVideoStatus(videoId) {
  return request(`/videos/${videoId}/status`)
}

export function getTranscript(videoId) {
  return request(`/videos/${videoId}/transcript`)
}

export function getTutorialSteps(videoId) {
  return request(`/videos/${videoId}/steps`)
}

export function getVideoEvidence(videoId) {
  return request(`/videos/${videoId}/evidence`)
}
