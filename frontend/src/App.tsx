import { Navigate, Route, Routes } from 'react-router-dom'
import { Shell } from './components/Shell'
import { ChatPage } from './pages/ChatPage'
import { GradePage } from './pages/GradePage'
import { HomePage } from './pages/HomePage'
import { LibraryPage } from './pages/LibraryPage'
import { StudioPage } from './pages/StudioPage'

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<HomePage />} />
        <Route path="library" element={<LibraryPage />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="studio" element={<StudioPage />} />
        <Route path="grade" element={<GradePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
