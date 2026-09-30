import { Link } from 'react-router-dom'

function PrivacyPolicyPage() {
  return (
    <div className="landing-page">
      <header className="landing-header">
        <div className="landing-header-inner">
          <Link to="/" className="landing-brand" aria-label="VideoMind home">
            <span className="landing-brand-mark">V</span>
            <span className="landing-brand-text">VideoMind</span>
          </Link>

          <nav className="landing-nav" aria-label="Privacy navigation">
            <Link to="/">Home</Link>
            <Link to="/#features">Features</Link>
          </nav>
        </div>
      </header>

      <main>
        <section className="landing-section" style={{ paddingTop: '72px', paddingBottom: '72px' }}>
          <div className="section-heading narrow-heading" style={{ textAlign: 'left', maxWidth: '760px' }}>
            <p className="section-kicker">Privacy Policy</p>
            <h2>Privacy policy</h2>
            <p className="section-copy" style={{ marginTop: '18px' }}>
              <strong>Draft for owner review. This page is not a final privacy policy.</strong>
            </p>
          </div>

          <div className="guide-panel" style={{ maxWidth: '820px', marginTop: '36px' }}>
            <div className="guide-header">
              <div>
                <p className="guide-label">Overview</p>
                <h3>Current information handling in this MVP</h3>
              </div>
            </div>

            <div className="guide-step-body" style={{ padding: '22px 22px 10px' }}>
              <div className="implementation-card" style={{ marginBottom: '14px' }}>
                <div className="implementation-line">
                  <span className="implementation-label">Early access</span>
                  <span>The signup endpoint stores the submitted name and email address in the application database. The form requires a contact checkbox, but its selection is not stored as a separate consent record.</span>
                </div>
              </div>

              <div className="implementation-card" style={{ marginBottom: '14px' }}>
                <div className="implementation-line">
                  <span className="implementation-label">Video analysis</span>
                  <span>For local uploads, the backend stores the source video on its configured filesystem and stores video metadata, transcript segments, detections, evidence, and tutorial steps in the application database. The source file may be temporary on deployments with an ephemeral filesystem.</span>
                </div>
              </div>

              <div className="implementation-card" style={{ marginBottom: '14px' }}>
                <div className="implementation-line">
                  <span className="implementation-label">YouTube URLs</span>
                  <span>The application stores the YouTube URL and analysis results in its database. Transcript retrieval uses the configured transcript provider or the local fallback. The service providers, data locations, and applicable retention details still require owner confirmation.</span>
                </div>
              </div>

              <div className="implementation-card" style={{ marginBottom: '14px' }}>
                <div className="implementation-line">
                  <span className="implementation-label">Retention and deletion</span>
                  <span>This MVP does not define a complete retention schedule or self-service deletion process. The responsible owner must confirm retention periods and a working request channel before launch.</span>
                </div>
              </div>

              <div className="implementation-card" style={{ marginBottom: '14px' }}>
                <div className="implementation-line">
                  <span className="implementation-label">Owner confirmation required</span>
                  <span>Before publication, confirm the responsible legal entity, effective date, privacy contact, retention and deletion process, hosting and transcript providers, and jurisdictions relevant to users. No legal entity, contact address, or retention period is asserted here.</span>
                </div>
              </div>

              <div className="implementation-card" style={{ marginBottom: '14px' }}>
                <div className="implementation-line">
                  <span className="implementation-label">Scope</span>
                  <span>This summary describes behavior found in the current repository and is provided for product-owner review. It is not legal advice or a statement that all production providers have been verified.</span>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="landing-footer">
        <div className="landing-footer-inner">
          <div>
            <p className="landing-footer-brand">VideoMind</p>
            <p className="landing-footer-tagline">Understand any video. Get what matters.</p>
          </div>

          <div className="landing-footer-links" aria-label="Footer links">
            <Link to="/">Home</Link>
            <Link to="/#features">Features</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}

export default PrivacyPolicyPage
