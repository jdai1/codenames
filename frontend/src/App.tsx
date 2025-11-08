function App() {
  const nCards = 5
  const mCards = 5

  return (
    <div className='flex flex-col h-screen'>
      <div className='h-24'>players</div>

      <div className='grid grid-cols-5 h-full'>
        <div className='col-span-1 bg-amber-300'>hello world</div>
        <div className='col-span-3 bg-amber-400'>
          <div className={`grid grid-cols-${mCards} grid-rows-${nCards}`}>
            {Array(25).fill(<div>hello</div>)}
          </div>
        </div>
        <div className='col-span-1 bg-amber-700'>hello world</div>
      </div>
    </div>
  )
}

export default App
