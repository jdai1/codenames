import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { cva } from 'class-variance-authority'
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
    spymaster: 'GPT4_1',
    guesser: 'GPT4_1',
  },
  blue: {
    spymaster: 'GPT4_1',
    guesser: 'GPT4_1',
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

type Actor = {
  actor_type: 'user' | 'llm'
  name: string
  model?: string // Only for LLM actors
}

type HintEventData = {
  card_amount: number
  team_color: TeamColor
  word: string
}

type GivenGuessData = {
  given_hint: HintEventData
  guessed_card: { word: string; color: CardColor | null }
  correct: boolean
}

type GameEvent = {
  actor: Actor
  event_type:
    | 'hint_given'
    | 'guess_made'
    | 'turn_passed'
    | 'chat_message'
    | 'operative_action'
  hint?: HintEventData // For hint_given events
  guess?: GivenGuessData // For guess_made events
  correct?: boolean // Flattened from guess.correct for guess_made events
  message?: string // For chat_message and operative_action events
  message_metadata?: Record<string, unknown> // For chat_message events
  tool?: string // For operative_action events (e.g., "talk")
  player_role: string
  team_color: TeamColor
  timestamp: string
}

type EventHistory = {
  blue_team: GameEvent[]
  global_events: GameEvent[]
  red_team: GameEvent[]
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
  event_history?: EventHistory
}

type CreateGameResponse = {
  game_id: string
  message: string
  game_state: GameState
}

function Game() {
  const [gameType, setGameType] = useState<GameType>(defaultGameType)
  const [redOperators, setRedOperators] = useState<number>(1)
  const [blueOperators, setBlueOperators] = useState<number>(1)
  const [gameId, setGameId] = useState<string | null>(null)
  const [spymasterView, setSpymasterView] = useState(false)

  const queryClient = useQueryClient()

  // Keyboard shortcut: Press Cmd+K (Mac) or Ctrl+K (Windows/Linux) to toggle spymaster view
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setSpymasterView((prev) => !prev)
      }
    }

    window.addEventListener('keydown', handleKeyDown)

    return () => {
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [])

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
      // Fetch and store the operative view (with show_colors=false) with history
      const operativeResponse = await fetch(
        new URL(
          `/games/${data.game_id}?show_colors=false&include_history=true`,
          API_URL
        ),
        {
          method: 'GET',
        }
      )
      if (operativeResponse.ok) {
        const operativeState = await operativeResponse.json()
        queryClient.setQueryData(['gameState', data.game_id], operativeState)
      }

      // Also store full state with history
      const fullResponse = await fetch(
        new URL(
          `/games/${data.game_id}?show_colors=true&include_history=true`,
          API_URL
        ),
        {
          method: 'GET',
        }
      )
      if (fullResponse.ok) {
        const fullState = await fullResponse.json()
        queryClient.setQueryData(['gameStateFull', data.game_id], fullState)
      }
    },
  })

  // Query for operative view (show_colors=false) - this is the main query that gets updated
  const { data: gameStateOperative, isLoading } = useQuery<GameState>({
    queryKey: ['gameState', gameId],
    queryFn: async () => {
      if (!gameId) return null
      const response = await fetch(
        new URL(
          `/games/${gameId}?show_colors=false&include_history=true`,
          API_URL
        ),
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
        new URL(
          `/games/${gameId}?show_colors=true&include_history=true`,
          API_URL
        ),
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

  // Map player type to model name
  const getModelName = (playerType: PlayerTypeId): string => {
    if (playerType === 'GPT4_1') return 'gpt-4.1'
    if (playerType === 'GEMINI') return 'gemini'
    if (playerType === 'GPT5') return 'gpt-5'
    if (playerType === 'CLAUDE_SONNET') return 'claude-sonnet'
    if (playerType === 'GEMINI_2_5_PRO') return 'gemini/gemini-2.5-pro'
    if (playerType === 'GROK_4') return 'xai/grok-4-fast-reasoning'
    if (playerType === 'KIMI_K2_THINKING') return 'kimi-k2-thinking'
    if (playerType === 'ZAI_4_6') return 'zai-4.6'
    if (playerType === 'OPENAI_OSS') return 'openai oss'
    if (playerType === 'QWEN_3_235B') return 'qwen 3 235b'
    if (playerType === 'DEEPSEEK_V3_2_EXP_THINKING')
      return 'deepseek v3.2-exp-thinking'
    if (playerType === 'LLAMA_3_1_405B') return 'llama 3.1 405b'
    return 'gpt-4.1' // default
  }

  // Track if we've already triggered AI action for current turn to prevent duplicate calls
  const aiActionTriggeredRef = useRef<string>('')
  // Track AI loading state: { team: 'RED' | 'BLUE', action: 'hint' | 'guess' } | null
  const [aiLoading, setAiLoading] = useState<{
    team: 'RED' | 'BLUE'
    action: 'hint' | 'guess'
  } | null>(null)

  // Auto-trigger AI actions when it's an AI's turn
  useEffect(() => {
    if (!gameState || !gameId || gameState.is_game_over) {
      aiActionTriggeredRef.current = ''
      setAiLoading(null)
      return
    }

    const currentTeam = gameState.current_turn.team
    const currentRole = gameState.current_turn.role
    const turnKey = `${currentTeam}-${currentRole}-${gameState.current_turn.left_guesses}`

    // Skip if we've already triggered for this turn
    if (aiActionTriggeredRef.current === turnKey) return

    const teamConfig = currentTeam === 'RED' ? gameType.red : gameType.blue
    const isAITurn =
      teamConfig[currentRole === 'HINTER' ? 'spymaster' : 'guesser'] !== 'HUMAN'

    if (isAITurn) {
      aiActionTriggeredRef.current = turnKey
      const model = getModelName(
        teamConfig[currentRole === 'HINTER' ? 'spymaster' : 'guesser']
      )

      if (currentRole === 'HINTER') {
        // AI Spymaster - give hint
        setAiLoading({ team: currentTeam, action: 'hint' })
        fetch(new URL(`/games/${gameId}/ai/hint`, API_URL), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ model }),
        })
          .then(async (response) => {
            console.log('AI hint response status:', response.status)
            console.log('AI hint response headers:', response.headers)

            if (!response.ok) {
              const text = await response.text()
              try {
                const error = JSON.parse(text)
                throw new Error(error.error || 'Failed to get AI hint')
              } catch (parseError) {
                console.error('Error parsing error response:', parseError)
                throw new Error(text || 'Failed to get AI hint')
              }
            }

            // Handle Server-Sent Events (SSE) stream
            const reader = response.body?.getReader()
            const decoder = new TextDecoder()
            let buffer = ''

            if (!reader) {
              throw new Error('Response body is not readable')
            }

            let done = false
            while (!done) {
              const result = await reader.read()
              done = result.done

              if (result.value) {
                buffer += decoder.decode(result.value, { stream: true })
                const lines = buffer.split('\n')
                buffer = lines.pop() || '' // Keep incomplete line in buffer

                for (const line of lines) {
                  if (line.startsWith('data: ')) {
                    const jsonStr = line.slice(6) // Remove 'data: ' prefix
                    try {
                      const data = JSON.parse(jsonStr)
                      console.log('AI hint SSE data:', data)

                      // Update game state with each SSE event
                      // Refetch game state to get latest updates including event history
                      const operativeResponse = await fetch(
                        new URL(
                          `/games/${gameId}?show_colors=false&include_history=true`,
                          API_URL
                        ),
                        {
                          method: 'GET',
                        }
                      )
                      if (operativeResponse.ok) {
                        const operativeState = await operativeResponse.json()
                        queryClient.setQueryData(
                          ['gameState', gameId],
                          operativeState
                        )
                      }

                      const fullResponse = await fetch(
                        new URL(
                          `/games/${gameId}?show_colors=true&include_history=true`,
                          API_URL
                        ),
                        {
                          method: 'GET',
                        }
                      )
                      if (fullResponse.ok) {
                        const fullState = await fullResponse.json()
                        queryClient.setQueryData(
                          ['gameStateFull', gameId],
                          fullState
                        )
                      }
                    } catch (parseError) {
                      console.error(
                        'Error parsing SSE data:',
                        parseError,
                        'Line:',
                        line
                      )
                    }
                  }
                }
              }
            }

            // Process any remaining buffer
            if (buffer.trim()) {
              if (buffer.startsWith('data: ')) {
                const jsonStr = buffer.slice(6)
                try {
                  const data = JSON.parse(jsonStr)
                  console.log('AI hint SSE final data:', data)

                  // Update game state with final SSE event
                  const operativeResponse = await fetch(
                    new URL(
                      `/games/${gameId}?show_colors=false&include_history=true`,
                      API_URL
                    ),
                    {
                      method: 'GET',
                    }
                  )
                  if (operativeResponse.ok) {
                    const operativeState = await operativeResponse.json()
                    queryClient.setQueryData(
                      ['gameState', gameId],
                      operativeState
                    )
                  }

                  const fullResponse = await fetch(
                    new URL(
                      `/games/${gameId}?show_colors=true&include_history=true`,
                      API_URL
                    ),
                    {
                      method: 'GET',
                    }
                  )
                  if (fullResponse.ok) {
                    const fullState = await fullResponse.json()
                    queryClient.setQueryData(
                      ['gameStateFull', gameId],
                      fullState
                    )
                  }
                } catch (parseError) {
                  console.error('Error parsing final SSE data:', parseError)
                }
              }
            }

            // Refetch game state after AI hint
            queryClient.invalidateQueries({ queryKey: ['gameState', gameId] })
            queryClient.invalidateQueries({
              queryKey: ['gameStateFull', gameId],
            })
            aiActionTriggeredRef.current = '' // Reset to allow next turn
            setAiLoading(null)
          })
          .catch((error) => {
            console.error('AI hint error:', error)
            aiActionTriggeredRef.current = '' // Reset on error
            setAiLoading(null)
          })
      } else if (currentRole === 'GUESSER') {
        // AI Guesser - make guess
        setAiLoading({ team: currentTeam, action: 'guess' })
        const nOperatives = currentTeam === 'RED' ? redOperators : blueOperators
        fetch(new URL(`/games/${gameId}/ai/guess`, API_URL), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ model, n_operatives: nOperatives }),
        })
          .then(async (response) => {
            console.log('AI guess response status:', response.status)
            console.log('AI guess response headers:', response.headers)

            if (!response.ok) {
              const text = await response.text()
              try {
                const error = JSON.parse(text)
                throw new Error(error.error || 'Failed to get AI guess')
              } catch (parseError) {
                console.error('Error parsing error response:', parseError)
                throw new Error(text || 'Failed to get AI guess')
              }
            }

            // Handle chunked streaming response
            const reader = response.body?.getReader()
            const decoder = new TextDecoder()
            let buffer = ''

            if (!reader) {
              throw new Error('Response body is not readable')
            }

            let done = false
            while (!done) {
              const result = await reader.read()
              done = result.done

              if (result.value) {
                buffer += decoder.decode(result.value, { stream: true })
                const lines = buffer.split('\n')
                buffer = lines.pop() || '' // Keep incomplete line in buffer

                for (const line of lines) {
                  if (line.trim() === '') continue // Skip empty lines

                  // Handle SSE format: "data: {...}"
                  if (line.startsWith('data: ')) {
                    const jsonStr = line.slice(6) // Remove 'data: ' prefix
                    try {
                      const data = JSON.parse(jsonStr)
                      console.log('AI guess SSE data:', data)

                      // Update game state with each chunk/event
                      // Refetch game state to get latest updates including event history
                      const operativeResponse = await fetch(
                        new URL(
                          `/games/${gameId}?show_colors=false&include_history=true`,
                          API_URL
                        ),
                        {
                          method: 'GET',
                        }
                      )
                      if (operativeResponse.ok) {
                        const operativeState = await operativeResponse.json()
                        queryClient.setQueryData(
                          ['gameState', gameId],
                          operativeState
                        )
                      }

                      const fullResponse = await fetch(
                        new URL(
                          `/games/${gameId}?show_colors=true&include_history=true`,
                          API_URL
                        ),
                        {
                          method: 'GET',
                        }
                      )
                      if (fullResponse.ok) {
                        const fullState = await fullResponse.json()
                        queryClient.setQueryData(
                          ['gameStateFull', gameId],
                          fullState
                        )
                      }

                      // Check if this is a completion or error event
                      if (data.type === 'complete' || data.type === 'error') {
                        done = true
                        break
                      }
                    } catch (parseError) {
                      console.error(
                        'Error parsing SSE data:',
                        parseError,
                        'Line:',
                        line
                      )
                    }
                  } else {
                    // Try parsing as direct JSON (in case it's not SSE format)
                    try {
                      const data = JSON.parse(line)
                      console.log('AI guess chunk data:', data)

                      // Update game state with each chunk
                      const operativeResponse = await fetch(
                        new URL(
                          `/games/${gameId}?show_colors=false&include_history=true`,
                          API_URL
                        ),
                        {
                          method: 'GET',
                        }
                      )
                      if (operativeResponse.ok) {
                        const operativeState = await operativeResponse.json()
                        queryClient.setQueryData(
                          ['gameState', gameId],
                          operativeState
                        )
                      }

                      const fullResponse = await fetch(
                        new URL(
                          `/games/${gameId}?show_colors=true&include_history=true`,
                          API_URL
                        ),
                        {
                          method: 'GET',
                        }
                      )
                      if (fullResponse.ok) {
                        const fullState = await fullResponse.json()
                        queryClient.setQueryData(
                          ['gameStateFull', gameId],
                          fullState
                        )
                      }

                      if (data.type === 'complete' || data.type === 'error') {
                        done = true
                        break
                      }
                    } catch (parseError) {
                      // Not JSON, skip this line
                      console.log('Skipping non-JSON line:', line)
                    }
                  }
                }
              }
            }

            // Process any remaining buffer
            if (buffer.trim()) {
              if (buffer.startsWith('data: ')) {
                const jsonStr = buffer.slice(6)
                try {
                  const data = JSON.parse(jsonStr)
                  console.log('AI guess final SSE data:', data)

                  // Final update
                  const operativeResponse = await fetch(
                    new URL(
                      `/games/${gameId}?show_colors=false&include_history=true`,
                      API_URL
                    ),
                    {
                      method: 'GET',
                    }
                  )
                  if (operativeResponse.ok) {
                    const operativeState = await operativeResponse.json()
                    queryClient.setQueryData(
                      ['gameState', gameId],
                      operativeState
                    )
                  }

                  const fullResponse = await fetch(
                    new URL(
                      `/games/${gameId}?show_colors=true&include_history=true`,
                      API_URL
                    ),
                    {
                      method: 'GET',
                    }
                  )
                  if (fullResponse.ok) {
                    const fullState = await fullResponse.json()
                    queryClient.setQueryData(
                      ['gameStateFull', gameId],
                      fullState
                    )
                  }
                } catch (parseError) {
                  console.error('Error parsing final SSE data:', parseError)
                }
              }
            }

            // Final refetch to ensure everything is up to date
            queryClient.invalidateQueries({ queryKey: ['gameState', gameId] })
            queryClient.invalidateQueries({
              queryKey: ['gameStateFull', gameId],
            })
            aiActionTriggeredRef.current = '' // Reset to allow next turn
            setAiLoading(null)
          })
          .catch((error) => {
            console.error('AI guess error:', error)
            aiActionTriggeredRef.current = '' // Reset on error
            setAiLoading(null)
          })
      }
    } else {
      // Reset when it's a human turn
      aiActionTriggeredRef.current = ''
      setAiLoading(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    gameState?.current_turn?.team,
    gameState?.current_turn?.role,
    gameState?.current_turn?.left_guesses,
    gameState?.is_game_over,
    gameId,
    gameType,
    redOperators,
    blueOperators,
    queryClient,
  ])

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

  // Handler for card clicks (guesses)
  const handleCardGuess = async (word: string) => {
    if (!gameId || !gameState) return

    const isGuesserTurn = gameState.current_turn.role === 'GUESSER'
    const currentTeam = gameState.current_turn.team
    const isHumanGuesser =
      (currentTeam === 'RED' ? gameType.red.guesser : gameType.blue.guesser) ===
      'HUMAN'

    if (isGuesserTurn && isHumanGuesser) {
      try {
        // Make the guess via API
        const response = await fetch(
          new URL(`/games/${gameId}/guess`, API_URL),
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ word }),
          }
        )

        if (!response.ok) {
          const error = await response.json()
          throw new Error(error.error || 'Failed to make guess')
        }

        // Explicitly refetch game state from the endpoint with history
        const operativeResponse = await fetch(
          new URL(
            `/games/${gameId}?show_colors=false&include_history=true`,
            API_URL
          ),
          {
            method: 'GET',
          }
        )
        if (operativeResponse.ok) {
          const operativeState = await operativeResponse.json()
          queryClient.setQueryData(['gameState', gameId], operativeState)
        }

        const fullResponse = await fetch(
          new URL(
            `/games/${gameId}?show_colors=true&include_history=true`,
            API_URL
          ),
          {
            method: 'GET',
          }
        )
        if (fullResponse.ok) {
          const fullState = await fullResponse.json()
          queryClient.setQueryData(['gameStateFull', gameId], fullState)
        }
      } catch (error) {
        console.error('Guess error:', error)
        // Error will be handled by the query invalidation refreshing the state
      }
    }
  }

  return (
    <div className='flex flex-col h-screen'>
      <div className='py-3 px-4 border-b border-gray-200 h-[100px] shrink-0'>
        <div className='flex items-center justify-center gap-8'>
          <div className='flex items-center gap-3'>
            <span className='text-red-600 font-semibold text-lg'>Red</span>
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
            {gameType.red.guesser !== 'HUMAN' && (
              <input
                type='number'
                className='border border-gray-300 p-1.5 w-12 text-md rounded'
                value={redOperators}
                onChange={(e) => setRedOperators(parseInt(e.target.value) || 1)}
                min='1'
              />
            )}
          </div>

          <button
            className={`rounded px-4 py-1.5 text-md transition-colors ${
              gameId
                ? 'bg-gray-300 hover:bg-gray-400 text-black font-normal'
                : 'bg-amber-400 hover:bg-amber-500 font-medium'
            }`}
            onClick={() => {
              if (gameId) {
                setGameId(null)
              } else {
                createNewGame.mutate()
              }
            }}
            disabled={createNewGame.isPending}
          >
            {createNewGame.isPending
              ? 'Creating...'
              : gameId
              ? 'Cancel'
              : 'Start'}
          </button>

          <div className='flex items-center gap-3'>
            <span className='text-blue-600 font-semibold text-lg'>Blue</span>
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
            {gameType.blue.guesser !== 'HUMAN' && (
              <input
                type='number'
                className='border border-gray-300 p-1.5 w-12 text-md rounded'
                value={blueOperators}
                onChange={(e) =>
                  setBlueOperators(parseInt(e.target.value) || 1)
                }
                min='1'
              />
            )}
          </div>
        </div>

        {gameState && (
          <div className='flex items-center justify-center mt-2'>
            <div className='text-xl'>
              {gameState.is_game_over && gameState.winner ? (
                <div className='flex items-center gap-2'>
                  <span
                    className={`font-extrabold tracking-wide ${
                      gameState.winner.team_color === 'RED'
                        ? 'text-red-600'
                        : 'text-cyan-700'
                    }`}
                  >
                    {gameState.winner.team_color} WINS
                  </span>
                  <span className='text-gray-600 font-medium text-base'>
                    • {gameState.winner.reason}
                  </span>
                </div>
              ) : (
                <>
                  <span
                    className={`font-extrabold tracking-wide ${
                      gameState.current_turn.team === 'RED'
                        ? 'text-red-600'
                        : 'text-cyan-700'
                    }`}
                  >
                    {gameState.current_turn.role === 'HINTER'
                      ? 'SPYMASTER'
                      : 'OPERATIVE'}
                  </span>
                  {gameState.current_turn.role === 'GUESSER' && (
                    <span className='text-gray-600 font-medium'>
                      {' '}
                      ({gameState.current_turn.left_guesses} left)
                    </span>
                  )}
                </>
              )}
            </div>
          </div>
        )}
      </div>

      {isLoading && (
        <div className='flex items-center justify-center h-full'>
          <div>Loading game...</div>
        </div>
      )}

      {gameState && (
        <div className='grid grid-cols-5 h-[calc(100vh-100px)] grow'>
          <div className='col-span-1 f overflow-scroll'>
            <ChatHistory
              team='RED'
              gameState={gameState}
              gameType={gameType.red}
              gameId={gameId!}
              onHintSubmitted={() => setSpymasterView(false)}
              aiLoading={aiLoading}
            />
          </div>
          <div className='col-span-3 bg-white p-4 overflow-scroll'>
            <div className='grid gap-2 grid-cols-5 grid-rows-5 h-full'>
              {gameState.board.map((card) => {
                const isGuesserTurn = gameState.current_turn.role === 'GUESSER'
                const currentTeam = gameState.current_turn.team
                const isHumanGuesser =
                  (currentTeam === 'RED'
                    ? gameType.red.guesser
                    : gameType.blue.guesser) === 'HUMAN'
                const canClick =
                  !spymasterView &&
                  !card.revealed &&
                  isGuesserTurn &&
                  isHumanGuesser

                return (
                  <Card
                    label={card.word}
                    type={getCardType(card)}
                    key={card.index}
                    onClick={
                      canClick ? () => handleCardGuess(card.word) : undefined
                    }
                    clickable={canClick}
                    revealed={card.revealed}
                    spymasterView={spymasterView}
                  />
                )
              })}
            </div>
          </div>
          <div className='col-span-1 bg-white overflow-scroll'>
            <ChatHistory
              team='BLUE'
              gameState={gameState}
              gameType={gameType.blue}
              aiLoading={aiLoading}
              gameId={gameId!}
              onHintSubmitted={() => setSpymasterView(false)}
            />
          </div>
        </div>
      )}

      {!gameState && !isLoading && (
        <div className='flex items-center justify-center h-full'>
          <div>Click "Start new game" to begin</div>
        </div>
      )}
    </div>
  )
}

const TEAM_NAME_TO_COLOR = {
  RED: 'text-red-600',
  BLUE: 'text-cyan-700',
}

// Editable display names for each model/provider
const MODEL_DISPLAY_NAME: Record<PlayerTypeId | 'HUMAN', string> = {
  HUMAN: 'Human',
  GPT4_1: 'GPT 4.1',
  GEMINI: 'Gemini',
  GPT5: 'GPT 5',
  CLAUDE_SONNET: 'Claude',
  GEMINI_2_5_PRO: 'Gemini',
  GROK_4: 'Grok',
  KIMI_K2_THINKING: 'Kimi',
  ZAI_4_6: 'Z.ai',
  OPENAI_OSS: 'OpenAI OSS',
  QWEN_3_235B: 'Qwen',
  DEEPSEEK_V3_2_EXP_THINKING: 'DeepSeek',
  LLAMA_3_1_405B: 'Llama',
}

type ChatHistoryProps = {
  team: 'RED' | 'BLUE'
  gameState: GameState
  gameType: { spymaster: PlayerTypeId; guesser: PlayerTypeId }
  gameId: string
  onHintSubmitted: () => void
  aiLoading: { team: 'RED' | 'BLUE'; action: 'hint' | 'guess' } | null
}

function ChatHistory({
  team,
  gameState,
  gameType,
  gameId,
  onHintSubmitted,
  aiLoading,
}: ChatHistoryProps) {
  const [hint, setHint] = useState('')
  const [hintCount, setHintCount] = useState('')
  const hintInputRef = useRef<HTMLInputElement>(null)
  const chatHistoryRef = useRef<HTMLDivElement>(null)
  const wasScrolledToBottomRef = useRef<boolean>(true)
  const queryClient = useQueryClient()
  const [expandedTalkEvents, setExpandedTalkEvents] = useState<Set<number>>(
    new Set()
  )

  const formatActorName = (name: string) => {
    const match = name.match(/op-(\d+)/i)
    if (match) {
      return `Operative ${match[1]}`
    }
    return name
  }

  const score = team === 'RED' ? gameState.score.red : gameState.score.blue

  const isCurrentTeam = gameState.current_turn.team === team
  const isSpymasterTurn =
    isCurrentTeam && gameState.current_turn.role === 'HINTER'
  const isGuesserTurn =
    isCurrentTeam && gameState.current_turn.role === 'GUESSER'
  const isHumanSpymaster = gameType.spymaster === 'HUMAN'
  const isHumanGuesser = gameType.guesser === 'HUMAN'
  const shouldEnableHintInput = isSpymasterTurn && isHumanSpymaster
  const shouldShowGuessMessage = isGuesserTurn && isHumanGuesser

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
    onSuccess: async () => {
      setHint('')
      setHintCount('')
      onHintSubmitted() // Turn off spymaster view

      // Explicitly refetch game state from the endpoint with history
      const operativeResponse = await fetch(
        new URL(
          `/games/${gameId}?show_colors=false&include_history=true`,
          API_URL
        ),
        {
          method: 'GET',
        }
      )
      if (operativeResponse.ok) {
        const operativeState = await operativeResponse.json()
        queryClient.setQueryData(['gameState', gameId], operativeState)
      }

      const fullResponse = await fetch(
        new URL(
          `/games/${gameId}?show_colors=true&include_history=true`,
          API_URL
        ),
        {
          method: 'GET',
        }
      )
      if (fullResponse.ok) {
        const fullState = await fullResponse.json()
        queryClient.setQueryData(['gameStateFull', gameId], fullState)
      }
    },
  })

  const passTurnMutation = useMutation({
    mutationFn: async () => {
      const response = await fetch(new URL(`/games/${gameId}/pass`, API_URL), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      })
      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.error || 'Failed to pass turn')
      }
      return response.json()
    },
    onSuccess: async () => {
      // Refetch game state after passing
      const operativeResponse = await fetch(
        new URL(
          `/games/${gameId}?show_colors=false&include_history=true`,
          API_URL
        ),
        {
          method: 'GET',
        }
      )
      if (operativeResponse.ok) {
        const operativeState = await operativeResponse.json()
        queryClient.setQueryData(['gameState', gameId], operativeState)
      }

      const fullResponse = await fetch(
        new URL(
          `/games/${gameId}?show_colors=true&include_history=true`,
          API_URL
        ),
        {
          method: 'GET',
        }
      )
      if (fullResponse.ok) {
        const fullState = await fullResponse.json()
        queryClient.setQueryData(['gameStateFull', gameId], fullState)
      }
    },
    onError: (error: Error) => {
      console.error('Pass turn error:', error)
    },
  })

  const handleSubmitHint = () => {
    const count = parseInt(hintCount)
    if (!hint || !count || count < 1) return
    giveHintMutation.mutate({ word: hint, card_amount: count })
  }

  const handlePassTurn = () => {
    passTurnMutation.mutate()
  }

  // Focus the input when it becomes enabled (human hinter's turn)
  useEffect(() => {
    if (shouldEnableHintInput && hintInputRef.current) {
      hintInputRef.current.focus()
    }
  }, [shouldEnableHintInput])

  // Track scroll position continuously
  useEffect(() => {
    const container = chatHistoryRef.current
    if (!container) return

    const handleScroll = () => {
      const isScrolledToBottom =
        container.scrollHeight - container.scrollTop <=
        container.clientHeight + 10 // 10px threshold for rounding
      wasScrolledToBottomRef.current = isScrolledToBottom
    }

    container.addEventListener('scroll', handleScroll)
    // Also check initial state
    handleScroll()

    return () => {
      container.removeEventListener('scroll', handleScroll)
    }
  }, [])

  // Auto-scroll chat history to bottom when new messages are added
  useEffect(() => {
    if (!chatHistoryRef.current || !gameState.event_history) return

    // Check if scrolled to bottom BEFORE the update (using the ref we stored)
    const shouldScrollToBottom = wasScrolledToBottomRef.current

    // Use requestAnimationFrame to ensure DOM has updated after React render
    requestAnimationFrame(() => {
      if (shouldScrollToBottom && chatHistoryRef.current) {
        chatHistoryRef.current.scrollTop = chatHistoryRef.current.scrollHeight
        // Update ref after scrolling to reflect new state
        wasScrolledToBottomRef.current = true
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    gameState.event_history?.red_team?.length,
    gameState.event_history?.blue_team?.length,
    team,
  ])

  return (
    <div className='p-4 flex flex-col h-full gap-3'>
      <HeaderWithLogo
        team={team}
        gameType={gameType}
        scoreText={`${score.revealed}/${score.total}`}
      />

      <div
        ref={chatHistoryRef}
        className='rounded-xl bg-white shadow-sm border border-gray-200/50 p-3 grow h-full flex flex-col gap-2.5 overflow-y-auto'
      >
        {gameState.event_history &&
          (team === 'RED'
            ? gameState.event_history.red_team
            : gameState.event_history.blue_team
          ).map((event, idx) => {
            if (event.event_type === 'hint_given' && event.hint) {
              return (
                <div
                  key={`event-${idx}`}
                  className={`px-3 py-2.5 rounded-lg shadow-sm ${
                    team === 'RED'
                      ? 'bg-gradient-to-br from-red-100 to-red-200/80 border border-red-300/70'
                      : 'bg-gradient-to-br from-cyan-100 to-cyan-200/80 border border-cyan-300/70'
                  }`}
                >
                  <span className='font-semibold text-sm'>Hint:</span>{' '}
                  <span className='font-bold'>{event.hint.word}</span>{' '}
                  <span className='text-sm'>({event.hint.card_amount})</span>
                </div>
              )
            } else if (event.event_type === 'guess_made' && event.guess) {
              // this is correct, do not change
              const isCorrect = event.correct
              return (
                <div
                  key={`event-${idx}`}
                  className={`px-3 py-2 rounded-lg text-sm shadow-sm border ${
                    isCorrect
                      ? 'bg-gradient-to-br from-green-100 to-green-200/70 border-green-300/70'
                      : 'bg-gradient-to-br from-gray-50 to-gray-100/50 border-gray-200/50'
                  }`}
                >
                  <span className='text-gray-700'>Guessed:</span>{' '}
                  <span className='font-semibold'>
                    {event.guess.guessed_card.word}
                  </span>{' '}
                  <span
                    className={
                      isCorrect
                        ? 'text-green-700 font-semibold'
                        : 'text-red-600'
                    }
                  >
                    {isCorrect ? '✓ Correct' : '✗ Wrong'}
                  </span>
                </div>
              )
            } else if (event.event_type === 'turn_passed') {
              return (
                <div
                  key={`event-${idx}`}
                  className='px-3 py-2 rounded-lg bg-gray-200 from-gray-50 to-gray-100/50 border border-gray-200/50 text-sm text-gray-600 italic shadow-sm'
                >
                  Passed turn
                </div>
              )
            } else if (event.event_type === 'chat_message' && event.message) {
              return (
                <div
                  key={`event-${idx}`}
                  className='px-3 py-2 rounded-lg bg-gray-200 from-blue-100 to-blue-200/70 border border-blue-300/70 text-sm italic shadow-sm'
                >
                  <span className='font-semibold not-italic text-blue-900'>
                    {formatActorName(event.actor.name)}:
                  </span>{' '}
                  {event.message}
                </div>
              )
            } else if (
              event.event_type === 'operative_action' &&
              event.tool === 'talk' &&
              event.message
            ) {
              const isExpanded = expandedTalkEvents.has(idx)
              const first20Chars = event.message.substring(0, 50)
              const hasMoreContent = event.message.length > 50
              const displayMessage = isExpanded
                ? event.message
                : hasMoreContent
                ? first20Chars + '...'
                : event.message

              return (
                <div
                  key={`event-${idx}`}
                  className='px-3 py-2.5 rounded-lg bg-gradient-to-br from-purple-50/40 to-gray-100/50 border border-purple-200/30 text-sm italic shadow-sm'
                >
                  <div className='font-semibold not-italic mb-1.5 text-purple-700/70'>
                    {formatActorName(event.actor.name)}:
                  </div>
                  <div className='whitespace-pre-wrap text-gray-600'>
                    {displayMessage}
                  </div>
                  {hasMoreContent && (
                    <button
                      onClick={() => {
                        setExpandedTalkEvents((prev) => {
                          const next = new Set(prev)
                          if (isExpanded) {
                            next.delete(idx)
                          } else {
                            next.add(idx)
                          }
                          return next
                        })
                      }}
                      className='mt-1.5 text-xs text-purple-500/70 hover:text-purple-700 font-medium transition-colors'
                    >
                      {isExpanded ? '▲ Show less' : '▼ Show more'}
                    </button>
                  )}
                </div>
              )
            } else if (
              event.event_type === 'operative_action' &&
              event.tool === 'vote_guess' &&
              event.message
            ) {
              return (
                <div
                  key={`event-${idx}`}
                  className='px-3 py-2 rounded-lg bg-gradient-to-br from-yellow-100 to-yellow-200/70 border border-yellow-300/70 text-sm italic shadow-sm'
                >
                  <span className='font-semibold not-italic text-yellow-900'>
                    {formatActorName(event.actor.name)}
                  </span>{' '}
                  <span className='text-gray-700'>voted: {event.message}</span>
                </div>
              )
            } else if (
              event.event_type === 'operative_action' &&
              event.tool === 'vote_pass' &&
              event.message
            ) {
              return (
                <div
                  key={`event-${idx}`}
                  className='px-3 py-2 rounded-lg bg-gradient-to-br from-emerald-100 to-emerald-200/70 border border-emerald-300/70 text-sm italic shadow-sm'
                >
                  <span className='font-semibold not-italic text-emerald-900'>
                    {formatActorName(event.actor.name)}
                  </span>{' '}
                  <span className='text-gray-700'>
                    voted to pass: {event.message}
                  </span>
                </div>
              )
            }
            return null
          })}
        {(!gameState.event_history ||
          (team === 'RED'
            ? gameState.event_history.red_team.length === 0
            : gameState.event_history.blue_team.length === 0)) &&
          !(aiLoading && aiLoading.team === team) && (
            <div className='text-gray-400 text-sm text-center py-8'>
              No activity yet
            </div>
          )}

        {aiLoading && aiLoading.team === team && (
          <div className='px-3 py-2 rounded-lg bg-gradient-to-br from-gray-50 to-gray-100/50 border border-gray-200/50 text-sm italic text-gray-600 shadow-sm animate-pulse'>
            {aiLoading.action === 'hint'
              ? '💭 AI is thinking of a hint...'
              : '🤔 AI is making guesses...'}
          </div>
        )}
      </div>

      {shouldShowGuessMessage ? (
        <div className='flex flex-col gap-2'>
          <div className='text-gray-500 text-xs text-center font-medium bg-white/50 py-1.5 rounded-lg'>
            Click on a card to make a guess
          </div>
          {gameState.current_turn.left_guesses > 0 && (
            <button
              className='rounded-lg bg-gradient-to-r from-gray-600 to-gray-700 hover:from-gray-700 hover:to-gray-800 p-2.5 text-white font-medium shadow-sm transition-all'
              disabled={passTurnMutation.isPending}
              onClick={handlePassTurn}
            >
              {passTurnMutation.isPending ? 'Passing...' : 'Pass Turn'}
            </button>
          )}
        </div>
      ) : isSpymasterTurn && isHumanSpymaster ? (
        <>
          <div className='flex gap-2'>
            <input
              ref={hintInputRef}
              type='text'
              className='border border-gray-300 rounded-lg p-2.5 grow min-w-0 shadow-sm focus:outline-none focus:ring-2 focus:ring-teal-500/50 focus:border-teal-500 transition-all'
              value={hint}
              onChange={(event) => setHint(event.target.value)}
              placeholder='Enter hint word'
              onKeyDown={(e) => {
                if (e.key === 'Enter' && hint && hintCount) {
                  handleSubmitHint()
                }
              }}
            />

            <input
              type='number'
              className='border border-gray-300 rounded-lg p-2.5 w-16 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-teal-500/50 focus:border-teal-500 transition-all'
              value={hintCount}
              onChange={(event) => setHintCount(event.target.value)}
              placeholder='#'
              min='1'
              onKeyDown={(e) => {
                if (e.key === 'Enter' && hint && hintCount) {
                  handleSubmitHint()
                }
              }}
            />
          </div>

          <button
            className='rounded-lg bg-gradient-to-r from-teal-500 to-teal-600 hover:from-teal-600 hover:to-teal-700 p-2.5 text-white font-medium shadow-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed'
            disabled={!hint || !hintCount || giveHintMutation.isPending}
            onClick={handleSubmitHint}
          >
            {giveHintMutation.isPending ? 'Submitting...' : 'Submit Hint'}
          </button>
        </>
      ) : null}
    </div>
  )
}

function HeaderWithLogo({
  team,
  gameType,
  scoreText,
}: {
  team: 'RED' | 'BLUE'
  gameType: { spymaster: PlayerTypeId; guesser: PlayerTypeId }
  scoreText: string
}) {
  // Prefer showing an AI logo; fall back to human if both are human
  const preferredType =
    gameType.spymaster !== 'HUMAN'
      ? gameType.spymaster
      : gameType.guesser !== 'HUMAN'
      ? gameType.guesser
      : 'HUMAN'

  const logoSrc = (() => {
    switch (preferredType) {
      case 'HUMAN':
        return '/logos/human.svg'
      case 'GPT4_1':
      case 'GPT5':
      case 'OPENAI_OSS':
        return '/logos/openai.svg'
      case 'GEMINI':
      case 'GEMINI_2_5_PRO':
        return '/logos/gemini.png'
      case 'CLAUDE_SONNET':
        return '/logos/claude.png'
      case 'GROK_4':
        return '/logos/grok.png'
      case 'DEEPSEEK_V3_2_EXP_THINKING':
        return '/logos/deepseek.png'
      case 'QWEN_3_235B':
        return '/logos/qwen.png'
      case 'ZAI_4_6':
        return '/logos/zai.svg'
      case 'LLAMA_3_1_405B':
        return '/logos/meta.png'
      case 'KIMI_K2_THINKING':
        return '/logos/kimi.jpg'
      default:
        return ''
    }
  })()

  return (
    <h2
      className={`text-lg font-bold ${TEAM_NAME_TO_COLOR[team]} flex items-center gap-2`}
    >
      {logoSrc ? (
        <img
          src={logoSrc}
          alt='model logo'
          className='w-5 h-5 object-contain rounded-sm'
        />
      ) : null}
      <span>
        Team{' '}
        {MODEL_DISPLAY_NAME[preferredType] ??
          playerTypes[preferredType]?.label ??
          'Unknown'}{' '}
        {scoreText}
      </span>
    </h2>
  )
}

type CardProps = {
  label: string
  type: 'UNKNOWN' | 'NEUTRAL' | 'RED' | 'BLUE' | 'ASSASSIN'
  spymasterView: boolean
  onClick?: () => void
  clickable?: boolean
  revealed?: boolean
}

function Card({
  label,
  type,
  onClick,
  clickable,
  revealed,
  spymasterView,
}: CardProps) {
  const card = cva(
    [
      'bold',
      'border',
      'border-gray-300',
      'px-4',
      'text-center',
      'flex',
      'items-center',
      'justify-between',
    ],
    {
      variants: {
        type: {
          NEUTRAL: [
            'bg-[color:var(--color-code-names-neutral)]',
            'border-[color:var(--color-code-names-neutral)]',
          ],
          RED: [
            'bg-[color:var(--color-code-names-red)]',
            'text-white',
            'border-[color:var(--color-code-names-red)]',
          ],
          BLUE: [
            'bg-[color:var(--color-code-names-blue)]',
            'text-white',
            'border-[color:var(--color-code-names-blue)]',
          ],
          ASSASSIN: ['bg-black', 'text-white'],
          UNKNOWN: ['bg-gray-100'],
        },
      },
    }
  )

  const baseClasses = card({ type })
  const clickableClasses = clickable
    ? 'cursor-pointer hover:opacity-80 hover:shadow-xl hover:bg-white transition-all'
    : ''
  const disabledClasses = revealed ? 'cursor-not-allowed' : ''
  const opacityClasses = revealed && spymasterView ? 'opacity-25' : ''

  return (
    <div
      className={`${baseClasses} ${clickableClasses} ${disabledClasses} ${opacityClasses} p-4 flex flex-col justify-between items-stretch card-label gap-4 ${
        label.length > 10 ? 'text-[1.5vw]' : 'text-[1.75vw]'
      } border-8`}
      onClick={clickable && !revealed && onClick ? onClick : undefined}
    >
      <div className='flex justify-end'>
        {(revealed || spymasterView) && (
          <span className='flex justify-center mb-2'>
            {type === 'RED' && (
              <img
                src={'/red.svg'}
                alt='Red'
                style={{ width: 'min(3vw, 4vh)' }}
              />
            )}
            {type === 'BLUE' && (
              <img
                src={'/blue.svg'}
                alt='Blue'
                style={{ width: 'min(3vw, 4vh)' }}
              />
            )}
            {type === 'ASSASSIN' && (
              <img
                src={'/assassin.svg'}
                alt='Assassin'
                style={{ width: 'min(3vw, 4vh)' }}
              />
            )}
            {type === 'NEUTRAL' && (
              <img
                src={'/innocent.svg'}
                alt='Neutral'
                style={{ width: 'min(3vw, 4vh)' }}
              />
            )}
          </span>
        )}
      </div>
      <div className='py-2 px-4 bg-white text-black min-h-16 flex items-center justify-center'>
        {label}
        {/* {revealed ? ' ✓' : ''} */}
      </div>
    </div>
  )
}

type PlayerTypeId =
  | 'HUMAN'
  | 'GPT4_1'
  | 'GEMINI'
  | 'GPT5'
  | 'CLAUDE_SONNET'
  | 'GEMINI_2_5_PRO'
  | 'GROK_4'
  | 'KIMI_K2_THINKING'
  | 'ZAI_4_6'
  | 'OPENAI_OSS'
  | 'QWEN_3_235B'
  | 'DEEPSEEK_V3_2_EXP_THINKING'
  | 'LLAMA_3_1_405B'
type PlayerType = {
  label: string
  isAI: boolean
}

const playerTypes: Record<PlayerTypeId, PlayerType> = {
  HUMAN: { label: 'Human', isAI: false },
  GPT4_1: { label: 'GPT 4.1', isAI: true },
  GEMINI: { label: 'Gemini', isAI: true },
  GPT5: { label: 'GPT-5', isAI: true },
  CLAUDE_SONNET: { label: 'Claude Sonnet', isAI: true },
  GEMINI_2_5_PRO: { label: 'Gemini 2.5 Pro', isAI: true },
  GROK_4: { label: 'Grok-4', isAI: true },
  KIMI_K2_THINKING: { label: 'Kimi K2 Thinking', isAI: true },
  ZAI_4_6: { label: 'Zai 4.6', isAI: true },
  OPENAI_OSS: { label: 'OpenAI OSS', isAI: true },
  QWEN_3_235B: { label: 'Qwen 3 235B', isAI: true },
  DEEPSEEK_V3_2_EXP_THINKING: { label: 'DeepSeek v3.2 (Thinking)', isAI: true },
  LLAMA_3_1_405B: { label: 'Llama 3.1 405B', isAI: true },
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
      className='bg-gray-50 border border-gray-300 p-1.5 text-md rounded hover:bg-gray-100 transition-colors cursor-pointer'
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
