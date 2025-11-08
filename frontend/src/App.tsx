import { cva } from 'class-variance-authority'

function App() {
  const nCards = 5
  const mCards = 5

  return (
    <div className='flex flex-col h-screen'>
      <div className='p-4 flex justify-between'>
        <div className='flex gap-8'>
          <div className='flex gap-2 items-center'>
            <span className='text-red-600 font-bold'>Red Team:</span>
            <PlayerTypeSelect />
            <PlayerTypeSelect />
          </div>
          <div className='flex gap-2 items-center'>
            <span className='text-blue-600 font-bold'>Blue Team:</span>
            <PlayerTypeSelect />
            <PlayerTypeSelect />
          </div>
        </div>

        <span className='flex gap-2 items-center'>
          <label htmlFor='spymasterModeToggle'>Spymaster View</label>

          <input id='spymasterModeToggle' type='checkbox' />
        </span>
      </div>

      <div className='grid grid-cols-5 h-full'>
        <div className='col-span-1 bg-gray-100'>hello world</div>
        <div className='col-span-3 bg-gray-200 p-4'>
          <div className={`grid grid-cols-${mCards} grid-rows-${nCards} gap-2`}>
            {Array(25).fill(<Card label='hello' type='UNKNOWN' />)}
          </div>
        </div>
        <div className='col-span-1 bg-gray-100'>hello world</div>
      </div>
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
          RED: ['bg-red-100'],
          BLUE: ['bg-blue-100'],
          ASSASSIN: ['bg-black-100', 'text-white'],
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

function PlayerTypeSelect() {
  return (
    <select className='bg-gray-100 p-2 rounded'>
      {Object.entries(playerTypes).map(([, value]) => {
        return <option value={value.label}>{value.label}</option>
      })}
    </select>
  )
}

export default App
