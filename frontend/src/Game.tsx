import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { cva } from 'class-variance-authority'
import { useState, useRef, useEffect } from 'react'
import { useState, useRef, useEffect } from 'react'

const API_URL = 'http://localhost:8080'

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

type TeamColor = 'BLUE' | 'RED'

type PlayerRole = 'HINTER' | 'GUESSER'

type CardColor = 'RED' | 'BLUE' | 'GRAY' | 'BLACK' | null

type CardWithIndex = {
  index: number
  word: string
  color: CardColor
  revealed: boolean
}

type Score = {
  blue: { revealed: number; total: number }
  red: { revealed: number; total: number }
}

type TurnInfo = {
  team: TeamColor
  role: PlayerRole
  left_guesses: number
}

type GivenHint = {
  word: string
  card_amount: number
  team: TeamColor
}

type GameState = {
  game_id: string
  board: CardWithIndex[]
  score: Score
  current_turn: TurnInfo
  hints: GivenHint[]
  last_hint: GivenHint | null
  is_game_over: boolean
  winner: { team_color: TeamColor; reason: string } | null
  board_size: number
}

type CreateGameResponse = {
  game_id: string
  message: string
  game_state: GameState
}

function Game() {
  const [gameType, setGameType] = useState<GameType>(defaultGameType)
  const [gameId, setGameId] = useState<string | null>(null)
  const [spymasterView, setSpymasterView] = useState(false)

  const queryClient = useQueryClient()

  const createNewGame = useMutation({
    mutationFn: async () => {
      const response = await fetch(new URL('/games', API_URL), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({}),
      })
      if (!response.ok) {
        throw new Error('Failed to create game')
      }
      const data: CreateGameResponse = await response.json()
      return data
    },
    onSuccess: async (data) => {
      setGameId(data.game_id)
      // Store the full game state (with show_colors=true) for spymaster view
      queryClient.setQueryData(['gameStateFull', data.game_id], data.game_state)
      // Fetch and store the operative view (with show_colors=false)
      const operativeResponse = await fetch(
        new URL(`/games/${data.game_id}?show_colors=false`, API_URL),
        {
          method: 'GET',
        }
      )
      if (operativeResponse.ok) {
        const operativeState = await operativeResponse.json()
        queryClient.setQueryData(['gameState', data.game_id], operativeState)
      }
    },
  })

  // Query for operative view (show_colors=false) - this is the main query that gets updated
  const { data: gameStateOperative, isLoading } = useQuery<GameState>({
    queryKey: ['gameState', gameId],
    queryFn: async () => {
      if (!gameId) return null
      const response = await fetch(
        new URL(`/games/${gameId}?show_colors=false`, API_URL),
        {
          method: 'GET',
        }
      )
      if (!response.ok) {
        throw new Error('Failed to fetch game state')
      }
      return response.json()
    },
    enabled: !!gameId,
  })

  // Query for spymaster view (show_colors=true) - stored separately, only fetches if not in cache
  const { data: gameStateFull } = useQuery<GameState>({
    queryKey: ['gameStateFull', gameId],
    queryFn: async () => {
      if (!gameId) return null
      const response = await fetch(
        new URL(`/games/${gameId}?show_colors=true`, API_URL),
        {
          method: 'GET',
        }
      )
      if (!response.ok) {
        throw new Error('Failed to fetch game state')
      }
      return response.json()
    },
    enabled: !!gameId,
    staleTime: Infinity, // Never refetch spymaster view automatically
    gcTime: Infinity, // Keep in cache forever
  })

  // Use the appropriate game state based on spymasterView
  const gameState = spymasterView ? gameStateFull : gameStateOperative

  const getCardType = (card: CardWithIndex): CardProps['type'] => {
    if (!card.revealed && !spymasterView) {
      return 'UNKNOWN'
    }
    if (!card.color) {
      return 'UNKNOWN'
    }
    if (card.color === 'RED') return 'RED'
    if (card.color === 'BLUE') return 'BLUE'
    if (card.color === 'BLACK') return 'ASSASSIN'
    return 'NEUTRAL'
  }

  const boardSize = gameState?.board_size || 25
  const gridCols = Math.sqrt(boardSize)

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

        <button
          className='rounded bg-amber-400 p-2 px-4'
          onClick={() => {
            createNewGame.mutate()
          }}
          disabled={createNewGame.isPending}
        >
          {createNewGame.isPending ? 'Creating...' : 'Start game'}
        </button>

        {gameState && (
          <div className='flex items-center'>
            <div className='flex gap-6 items-center justify-center'>
              <div className='text-lg text-gray-600'>
                Current Turn: {gameState.current_turn.team} -{' '}
                {gameState.current_turn.role}
                {gameState.current_turn.role === 'GUESSER' &&
                  ` (${gameState.current_turn.left_guesses} guesses left)`}
              </div>
              {gameState.is_game_over && gameState.winner && (
                <div className='text-lg font-bold text-green-600'>
                  Game Over! Winner: {gameState.winner.team_color} -{' '}
                  {gameState.winner.reason}
                </div>
              )}
            </div>
          </div>
        )}

        <span className='flex gap-2 items-center'>
          <label htmlFor='spymasterModeToggle'>Spymaster View</label>
          <input
            id='spymasterModeToggle'
            className='w-6 h-6'
            type='checkbox'
            checked={spymasterView}
            onChange={(e) => setSpymasterView(e.target.checked)}
            disabled={!gameId}
          />
        </span>
      </div>

      {isLoading && (
        <div className='flex items-center justify-center h-full'>
          <div>Loading game...</div>
        </div>
      )}

      {gameState && (
        <div className='grid grid-cols-5 h-full'>
          <div className='col-span-1 bg-gray-100'>
            <ChatHistory
              team='RED'
              gameState={gameState}
              gameType={gameType.red}
              gameId={gameId!}
              onHintSubmitted={() => setSpymasterView(false)}
            />
          </div>
          <div className='col-span-3 bg-gray-200 p-4'>
            <div
              className='grid gap-2'
              style={{
                gridTemplateColumns: `repeat(${gridCols}, 1fr)`,
              }}
            >
              {gameState.board.map((card) => (
                <Card
                  label={card.word}
                  type={getCardType(card)}
                  key={card.index}
                />
              ))}
            </div>
          </div>
          <div className='col-span-1 bg-gray-100'>
            <ChatHistory
              team='BLUE'
              gameState={gameState}
              gameType={gameType.blue}
              gameId={gameId!}
              onHintSubmitted={() => setSpymasterView(false)}
            />
          </div>
        </div>
      )}

      {!gameState && !isLoading && (
        <div className='flex items-center justify-center h-full'>
          <div>Click "Start game" to begin</div>
        </div>
      )}
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
  gameState: GameState
  gameType: { spymaster: PlayerTypeId; guesser: PlayerTypeId }
  gameId: string
  onHintSubmitted: () => void
}

function ChatHistory({
  team,
  gameState,
  gameType,
  gameId,
  onHintSubmitted,
}: ChatHistoryProps) {
  const [hint, setHint] = useState('')
  const [hintCount, setHintCount] = useState('')
  const hintInputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  const score = team === 'RED' ? gameState.score.red : gameState.score.blue

  const isCurrentTeam = gameState.current_turn.team === team
  const isSpymasterTurn =
    isCurrentTeam && gameState.current_turn.role === 'HINTER'
  const isHumanSpymaster = gameType.spymaster === 'HUMAN'
  const shouldEnableHintInput = isSpymasterTurn && isHumanSpymaster

  const giveHintMutation = useMutation({
    mutationFn: async ({
      word,
      card_amount,
    }: {
      word: string
      card_amount: number
    }) => {
      const response = await fetch(new URL(`/games/${gameId}/hint`, API_URL), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ word, card_amount }),
      })
      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.error || 'Failed to give hint')
      }
      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['gameState', gameId] })
      queryClient.invalidateQueries({ queryKey: ['gameStateFull', gameId] })
      setHint('')
      setHintCount('')
      onHintSubmitted() // Turn off spymaster view
    },
  })

  const handleSubmitHint = () => {
    const count = parseInt(hintCount)
    if (!hint || !count || count < 1) return
    giveHintMutation.mutate({ word: hint, card_amount: count })
  }

  // Focus the input when it becomes enabled (human hinter's turn)
  useEffect(() => {
    if (shouldEnableHintInput && hintInputRef.current) {
      hintInputRef.current.focus()
    }
  }, [shouldEnableHintInput])

  return (
    <div className='p-4 flex flex-col h-full gap-4'>
      <h2 className={`text-lg font-bold ${TEAM_NAME_TO_COLOR[team]}`}>
        Team {TEAM_NAME_TO_LABEL[team]} {score.revealed}/{score.total}
      </h2>

      <div className='border border-gray-300 p-2 grow h-full flex flex-col gap-2'>
        <div className='p-2 bg-red-100 rounded'>Hint: automobile 6</div>
      </div>

      <div className='flex gap-2'>
        <input
          ref={hintInputRef}
          type='text'
          className='border border-gray-300 p-2 grow min-w-0'
          value={hint}
          onChange={(event) => setHint(event.target.value)}
          disabled={!shouldEnableHintInput}
          placeholder={shouldEnableHintInput ? 'Enter hint word' : ''}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && hint && hintCount) {
              handleSubmitHint()
            }
          }}
        />

        <input
          type='number'
          className='border border-gray-300 p-2 w-16'
          value={hintCount}
          onChange={(event) => setHintCount(event.target.value)}
          disabled={!shouldEnableHintInput}
          placeholder={shouldEnableHintInput ? '#' : ''}
          min='1'
          onKeyDown={(e) => {
            if (e.key === 'Enter' && hint && hintCount) {
              handleSubmitHint()
            }
          }}
        />
      </div>

      <button
        className='rounded bg-teal-500 p-2'
        disabled={
          !hint ||
          !hintCount ||
          !shouldEnableHintInput ||
          giveHintMutation.isPending
        }
        onClick={handleSubmitHint}
      >
        {giveHintMutation.isPending ? 'Submitting...' : 'Submit hint'}
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

export default Game
