import { NavLink, Outlet } from 'react-router-dom'

const IconHome = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
    <path d="M4 10.5L12 4l8 6.5V20a1 1 0 01-1 1h-5v-6H10v6H5a1 1 0 01-1-1v-9.5z" />
  </svg>
)
const IconBook = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
    <path d="M4 5a2 2 0 012-2h12a2 2 0 012 2v14a1 1 0 01-1 1H6a2 2 0 00-2 2 0 0 01-2-2V5z" />
    <path d="M8 2v20" />
  </svg>
)
const IconChat = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
    <path d="M21 12a7 7 0 01-7 7H8l-5 3v-3H5a7 7 0 117-7h6z" />
  </svg>
)
const IconLines = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
    <path d="M4 7h16M4 12h16M4 17h10" strokeLinecap="round" />
  </svg>
)
const IconDeck = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
    <rect x="4" y="3" width="16" height="12" rx="2" />
    <path d="M8 21h8M12 15v6" strokeLinecap="round" />
  </svg>
)
const IconMark = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
    <circle cx="12" cy="12" r="8" />
    <path d="M12 8v4l2 2" strokeLinecap="round" />
  </svg>
)
const IconGrade = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
    <path d="M4 20h16M6 16l4-12 4 12M9 13h6" />
  </svg>
)

const links = [
  { to: '/', label: 'Home', Icon: IconHome },
  { to: '/library', label: 'Library', Icon: IconBook },
  { to: '/chat', label: 'Dialogue', Icon: IconChat },
  { to: '/summarize', label: 'Summarize', Icon: IconLines },
  { to: '/slides', label: 'Slides', Icon: IconDeck },
  { to: '/quiz', label: 'Quiz', Icon: IconMark },
  { to: '/grade', label: 'Grading', Icon: IconGrade },
]

export function Shell() {
  return (
    <div className="atelier">
      <aside className="rail">
        <div className="rail__brand">
          <div className="rail__mark" aria-hidden>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
              <path
                d="M6 4h6a4 4 0 014 4v12a1 1 0 01-1 1H6a2 2 0 01-2-2V6a2 2 0 012-2z"
                stroke="white"
                strokeWidth="1.6"
              />
              <path d="M9 8h4M9 12h4M9 16h2" stroke="white" strokeWidth="1.4" strokeLinecap="round" />
            </svg>
          </div>
          <span className="rail__tag">USJ Capstone</span>
          <span className="rail__title">Smart Teacher Assistant</span>
        </div>
        <nav className="nav nav--stack" aria-label="Main">
          {links.map(({ to, label, Icon }) => (
            <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => (isActive ? 'active' : '')}>
              <Icon />
              {label}
            </NavLink>
          ))}
        </nav>
        <p className="rail__foot">
          Each tool has its own screen — upload or pick a document where needed. Start the API on port 8000.
        </p>
      </aside>
      <main className="canvas">
        <div className="canvas__inner">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
