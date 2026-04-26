import { Navigate, Route, Routes } from 'react-router-dom'
import { Shell } from './components/Shell'
import { ChatPage } from './pages/ChatPage'
import { GeneratePage } from './pages/GeneratePage'
import { GradePage } from './pages/GradePage'
import { HomePage } from './pages/HomePage'
import { LibraryPage } from './pages/LibraryPage'
import { QuizPage } from './pages/QuizPage'
import { SlidesPage } from './pages/SlidesPage'
import { SummarizePage } from './pages/SummarizePage'

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<HomePage />} />
        <Route path="library" element={<LibraryPage />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="summarize" element={<SummarizePage />} />
        <Route path="slides" element={<SlidesPage />} />
        <Route path="quiz" element={<QuizPage />} />
        <Route path="generate" element={<GeneratePage />} />
        <Route path="grade" element={<GradePage />} />
        <Route path="studio" element={<Navigate to="/summarize" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
