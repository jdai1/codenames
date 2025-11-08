import { cva } from 'class-variance-authority'
import { useState } from 'react'

const nouns = [
  'Lantern',
  'Bridge',
  'Notebook',
  'Glacier',
  'Compass',
  'Thunder',
  'Garden',
  'Mirror',
  'Anchor',
  'Feather',
  'Train',
  'Horizon',
  'Wallet',
  'Tower',
  'Puzzle',
  'Candle',
  'River',
  'Helmet',
  'Clock',
  'Carpet',
  'Storm',
  'Telescope',
  'Apple',
  'Window',
  'Map',
]

type GameType = {
  red: {
    spymaster: PlayerTypeId
    guesser: PlayerTypeId
  }
  blue: {
    spymaster: PlayerTypeId
    guesser: PlayerTypeId
  }
}

const defaultGameType = {
  red: {
    spymaster: 'GPT5',
    guesser: 'GPT5',
  },
  blue: {
    spymaster: 'GPT5',
    guesser: 'GPT5',
  },
} as const

function App() {
  const nCards = 5
  const mCards = 5

  const [gameType, setGameType] = useState<GameType>(defaultGameType)

  const [cards] = useState<
    {
      label: string
      type: CardProps['type']
    }[]
  >(nouns.map((word) => ({ label: word, type: 'UNKNOWN' as const })))

  return (
    <div className='flex flex-col h-screen'>
      <div className='p-4 flex justify-between'>
        <div className='flex gap-8'>
          <div className='flex gap-2 items-center'>
            <span className='text-red-600 font-bold'>Red Team:</span>
            <PlayerTypeSelect
              value={gameType.red.spymaster}
              onChange={(value: PlayerTypeId) =>
                setGameType((prev: GameType) => ({
                  ...prev,
                  red: { ...prev.red, spymaster: value },
                }))
              }
            />
            <PlayerTypeSelect
              value={gameType.red.guesser}
              onChange={(value: PlayerTypeId) =>
                setGameType((prev: GameType) => ({
                  ...prev,
                  red: { ...prev.red, guesser: value },
                }))
              }
            />
          </div>
          <div className='flex gap-2 items-center'>
            <span className='text-blue-600 font-bold'>Blue Team:</span>
            <PlayerTypeSelect
              value={gameType.blue.spymaster}
              onChange={(value: PlayerTypeId) =>
                setGameType((prev: GameType) => ({
                  ...prev,
                  blue: { ...prev.blue, spymaster: value },
                }))
              }
            />
            <PlayerTypeSelect
              value={gameType.blue.guesser}
              onChange={(value: PlayerTypeId) =>
                setGameType((prev: GameType) => ({
                  ...prev,
                  blue: { ...prev.blue, guesser: value },
                }))
              }
            />
          </div>
        </div>

        <button className='rounded bg-amber-400 p-2 px-4'>Start game</button>

        <button className='rounded bg-amber-400 p-2 px-4'>Start game</button>

        <span className='flex gap-2 items-center'>
          <label htmlFor='spymasterModeToggle'>Spymaster View</label>

          <input id='spymasterModeToggle' type='checkbox' />
        </span>
      </div>

      <div className='grid grid-cols-5 h-full'>
        <div className='col-span-1 bg-gray-100'>
          <ChatHistory team='RED' />
        </div>
        <div className='col-span-1 bg-gray-100'>
          <ChatHistory team='RED' />
        </div>
        <div className='col-span-3 bg-gray-200 p-4'>
          <div className={`grid grid-cols-${mCards} grid-rows-${nCards} gap-2`}>
            {cards.map((card) => (
              <Card label={card.label} type={card.type} />
            ))}
            {cards.map((card) => (
              <Card label={card.label} type={card.type} />
            ))}
          </div>
        </div>
        <div className='col-span-1 bg-gray-100'>
          <ChatHistory team='BLUE' />
        </div>
        <div className='col-span-1 bg-gray-100'>
          <ChatHistory team='BLUE' />
        </div>
      </div>
    </div>
  )
}

const TEAM_NAME_TO_LABEL = {
  RED: 'Red',
  BLUE: 'Blue',
}

const TEAM_NAME_TO_COLOR = {
  RED: 'text-red-600',
  BLUE: 'text-blue-600',
}

type ChatHistoryProps = {
  team: 'RED' | 'BLUE'
}

function ChatHistory({ team }: ChatHistoryProps) {
  const [hint, setHint] = useState('')

  return (
    <div className='p-4 flex flex-col h-full gap-4'>
      <h2 className={`text-lg font-bold ${TEAM_NAME_TO_COLOR[team]}`}>
        Team {TEAM_NAME_TO_LABEL[team]} 6/7
      </h2>

      <div className='border border-gray-300 p-2 grow h-full flex flex-col gap-2'>
        <div className='p-2 bg-red-100 rounded'>Hint: automobile 6</div>
      </div>

      <input
        type='text'
        className='border border-gray-300 p-2'
        value={hint}
        onChange={(event) => setHint(event.target.value)}
      />

      <button className='rounded bg-teal-500 p-2' disabled={!hint}>
        Submit hint
      </button>
    </div>
  )
}

type CardProps = {
  label: string
  type: 'UNKNOWN' | 'NEUTRAL' | 'RED' | 'BLUE' | 'ASSASSIN'
}

function Card({ label, type }: CardProps) {
  const card = cva(
    ['bold', 'border', 'border-gray-300', 'px-4 py-8', 'text-center'],
    {
      variants: {
        type: {
          NEUTRAL: ['bg-amber-100'],
          RED: ['bg-red-800', 'text-white', 'border-red-800'],
          BLUE: ['bg-blue-800', 'text-white', 'border-blue-800'],
          ASSASSIN: ['bg-black', 'text-white'],
          RED: ['bg-red-800', 'text-white', 'border-red-800'],
          BLUE: ['bg-blue-800', 'text-white', 'border-blue-800'],
          ASSASSIN: ['bg-black', 'text-white'],
          UNKNOWN: ['bg-gray-100'],
        },
      },
    }
  )
  return <div className={card({ type })}>{label}</div>
}

type PlayerTypeId = 'HUMAN' | 'GPT5' | 'GEMINI'
type PlayerType = {
  label: string
  isAI: boolean
}

const playerTypes: Record<PlayerTypeId, PlayerType> = {
  HUMAN: { label: 'Human', isAI: false },
  GPT5: { label: 'GPT-5', isAI: true },
  GEMINI: { label: 'Gemini', isAI: true },
}

function PlayerTypeSelect({
  value,
  onChange,
}: {
  value: PlayerTypeId
  onChange: (value: PlayerTypeId) => void
}) {
  return (
    <select
      className='bg-gray-100 p-2 rounded'
      value={value}
      onChange={(event) => {
        onChange(event.target.value as PlayerTypeId)
      }}
    >
      {Object.entries(playerTypes).map(([key, pt]) => (
        <option key={key} value={key}>
          {pt.label}
        </option>
      ))}
    </select>
  )
}

export default App
