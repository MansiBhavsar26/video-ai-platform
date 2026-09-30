import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

function isValidEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)
}

function normalizeEmail(value) {
  return value.trim().toLowerCase()
}

function EarlyAccessModal({ isOpen, onClose }) {
  const [formData, setFormData] = useState({ name: '', email: '', consent: false })
  const [errors, setErrors] = useState({})
  const [isSubmitted, setIsSubmitted] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitMessage, setSubmitMessage] = useState('')

  const resetState = useCallback(() => {
    setFormData({ name: '', email: '', consent: false })
    setErrors({})
    setIsSubmitted(false)
    setIsSubmitting(false)
    setSubmitMessage('')
  }, [])

  const handleClose = useCallback(() => {
    resetState()
    onClose()
  }, [onClose, resetState])

  useEffect(() => {
    if (!isOpen) {
      return undefined
    }

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        handleClose()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleClose, isOpen])

  const canSubmit = useMemo(
    () => {
      const trimmedName = formData.name.trim()
      const trimmedEmail = normalizeEmail(formData.email)
      return (
        trimmedName &&
        trimmedEmail &&
        isValidEmail(trimmedEmail) &&
        formData.consent &&
        !errors.email &&
        !isSubmitting
      )
    },
    [errors.email, formData.consent, formData.email, formData.name, isSubmitting],
  )

  const handleChange = (event) => {
    const { name, value, type, checked } = event.target
    const nextValue = type === 'checkbox' ? checked : value

    setFormData((previous) => ({ ...previous, [name]: nextValue }))

    if (errors[name]) {
      setErrors((previous) => ({ ...previous, [name]: '' }))
    }

    if (name === 'email' && value) {
      const normalized = normalizeEmail(value)
      setErrors((previous) => ({
        ...previous,
        email: isValidEmail(normalized) ? '' : 'Please enter a valid email address.',
      }))
    }
  }

  const handleSubmit = async (event) => {
    event.preventDefault()

    const nextErrors = {}
    const trimmedName = formData.name.trim()
    const normalizedEmail = normalizeEmail(formData.email)

    if (!trimmedName) {
      nextErrors.name = 'Please enter your name.'
    }

    if (!normalizedEmail) {
      nextErrors.email = 'Please enter your email.'
    } else if (!isValidEmail(normalizedEmail)) {
      nextErrors.email = 'Please enter a valid email address.'
    }

    if (!formData.consent) {
      nextErrors.consent = 'Please confirm that you consent to being contacted.'
    }

    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors)
      return
    }

    setIsSubmitting(true)
    setSubmitMessage('')
    setErrors({})

    try {
      const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || ''
      const endpoint = `${apiBaseUrl.replace(/\/$/, '')}/api/early-access`

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: trimmedName,
          email: normalizedEmail,
          consent: true,
        }),
      })

      let payload = null

      try {
        payload = await response.json()
      } catch  {
        payload = null
      }

      if (!response.ok || !payload?.success) {
        const message = payload?.message || 'The early-access form is currently unavailable. Please try again later.'
        setSubmitMessage(message)
        setIsSubmitted(false)
        return
      }

      setIsSubmitted(true)
      setSubmitMessage(payload.message || 'Thanks for joining early access.')
    } catch  {
      setSubmitMessage('The early-access form is currently unavailable. Please try again later.')
      setIsSubmitted(false)
    } finally {
      setIsSubmitting(false)
    }
  }

  if (!isOpen) {
    return null
  }

  return (
    <div
      className="early-access-backdrop"
      onClick={handleClose}
      role="presentation"
    >
      <div
        className="early-access-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="early-access-title"
        onClick={(event) => event.stopPropagation()}
      >
        <button
          type="button"
          className="modal-close-button"
          aria-label="Close early access form"
          onClick={handleClose}
        >
          ×
        </button>

        {isSubmitted ? (
          <div className="early-access-success">
            <div className="success-badge">✓</div>
            <h3 id="early-access-title">You’re on the list.</h3>
            <p>
              {submitMessage || 'Thanks for your interest in VideoMind. We will reach out when early access opens.'}
            </p>
            <button type="button" className="modal-primary-button" onClick={handleClose}>
              Close
            </button>
          </div>
        ) : (
          <>
            <p className="modal-kicker">Early access</p>
            <h3 id="early-access-title">Join the first wave.</h3>
            <p className="modal-copy">
              VideoMind is still being built. Join the early-access list to follow the launch and get access when we’re ready.
            </p>

            <form className="early-access-form" onSubmit={handleSubmit} noValidate>
              <div className="field-group">
                <label htmlFor="early-access-name">Name</label>
                <input
                  id="early-access-name"
                  name="name"
                  type="text"
                  value={formData.name}
                  onChange={handleChange}
                  placeholder="Your name"
                  autoComplete="name"
                  aria-invalid={Boolean(errors.name)}
                />
                {errors.name && <span className="field-error">{errors.name}</span>}
              </div>

              <div className="field-group">
                <label htmlFor="early-access-email">Email</label>
                <input
                  id="early-access-email"
                  name="email"
                  type="email"
                  value={formData.email}
                  onChange={handleChange}
                  placeholder="you@example.com"
                  autoComplete="email"
                  aria-invalid={Boolean(errors.email)}
                />
                {errors.email && <span className="field-error">{errors.email}</span>}
              </div>

              <div className="field-group consent-group">
                <label htmlFor="early-access-consent" className="consent-checkbox-label">
                  <input
                    id="early-access-consent"
                    name="consent"
                    type="checkbox"
                    checked={formData.consent}
                    onChange={handleChange}
                    aria-invalid={Boolean(errors.consent)}
                  />
                  <span>
                    I agree to be contacted about early access and product updates. My name and email are stored for this purpose; this checkbox choice is not stored separately. See the{' '}
                    <Link to="/privacy-policy" onClick={handleClose}>Privacy Policy</Link>.
                  </span>
                </label>
                {errors.consent && <span className="field-error">{errors.consent}</span>}
              </div>

              {submitMessage && !isSubmitted && <p className="field-error" role="alert">{submitMessage}</p>}

              <button type="submit" className="modal-primary-button" disabled={!canSubmit}>
                {isSubmitting ? 'Submitting…' : 'Join Early Access'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  )
}

export default EarlyAccessModal
