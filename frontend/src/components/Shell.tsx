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
const IconSpark = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 2l1.8 5.5h5.7l-4.6 3.4 1.8 5.6L12 15.9 7.3 16.5l1.8-5.6L4.5 7.5h5.7L12 2z" opacity="0.92" />
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
  { to: '/studio', label: 'Studio', Icon: IconSpark },
  { to: '/grade', label: 'Grading salon', Icon: IconGrade },
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
        <nav className="nav" aria-label="Main">
          {links.map(({ to, label, Icon }) => (
            <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => (isActive ? 'active' : '')}>
              <Icon />
              {label}
            </NavLink>
          ))}
        </nav>
        <p className="rail__foot">
          Teaching as craft — documents, dialogue, and fair grading in one calm workspace.
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
