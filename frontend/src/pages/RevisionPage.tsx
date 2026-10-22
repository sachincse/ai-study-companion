import { useSearchParams } from 'react-router-dom'
import { SummariesTab, KeywordsTab } from '../components/revision/ArtifactTabs'
import { ConceptMapTab } from '../components/revision/ConceptMapTab'
import { FlashcardsTab } from '../components/revision/FlashcardsTab'
import { StudyPlanTab } from '../components/revision/StudyPlanTab'
import { PageHeader, Tabs } from '../components/ui'

type Tab = 'flashcards' | 'summaries' | 'keywords' | 'maps' | 'plan'
const TABS: { id: Tab; label: string }[] = [
  { id: 'flashcards', label: 'Flashcards' },
  { id: 'summaries', label: 'Summaries' },
  { id: 'keywords', label: 'Keywords' },
  { id: 'maps', label: 'Concept maps' },
  { id: 'plan', label: 'Study plan' },
]

export function RevisionPage() {
  const [params, setParams] = useSearchParams()
  const tab = (params.get('tab') as Tab) || 'flashcards'
  return (
    <div className="space-y-5 animate-fade-up">
      <PageHeader title="Revision Studio" subtitle="Spaced-repetition flashcards, exam summaries, keyword sheets, concept maps and a day-by-day plan, all generated from your material." />
      <Tabs tabs={TABS} value={TABS.some((t) => t.id === tab) ? tab : 'flashcards'} onChange={(t) => setParams({ tab: t })} />
      {tab === 'summaries' ? <SummariesTab /> : tab === 'keywords' ? <KeywordsTab /> : tab === 'maps' ? <ConceptMapTab /> : tab === 'plan' ? <StudyPlanTab /> : <FlashcardsTab />}
    </div>
  )
}
