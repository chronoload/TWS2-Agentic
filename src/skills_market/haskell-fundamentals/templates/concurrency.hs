-- Concurrency Template
-- Concurrent and parallel programming patterns

{-# LANGUAGE ScopedTypeVariables #-}

module Main where

import Control.Concurrent
import Control.Concurrent.Async
import Control.Concurrent.STM
import Control.Monad
import System.Random

-- | Basic thread example
basicThread :: IO ()
basicThread = do
    putStrLn "Starting thread..."
    threadId <- forkIO $ do
        forM_ [1..5 :: Int] $ \i -> do
            threadDelay 100000  -- 100ms
            putStrLn $ "Thread: " ++ show i
    threadDelay 500000  -- Wait 500ms
    killThread threadId
    putStrLn "Thread killed"

-- | MVar for synchronization
mvarExample :: IO ()
mvarExample = do
    mvar <- newEmptyMVar
    
    _ <- forkIO $ do
        putStrLn "Producer: working..."
        threadDelay 500000
        putMVar mvar "Result"
        putStrLn "Producer: done"
    
    putStrLn "Consumer: waiting..."
    result <- takeMVar mvar
    putStrLn $ "Consumer: got " ++ result

-- | Channel for communication
channelExample :: IO ()
channelExample = do
    chan <- newChan
    
    -- Producer
    _ <- forkIO $ do
        forM_ [1..5 :: Int] $ \i -> do
            writeChan chan i
            threadDelay 100000
        writeChan chan (-1)  -- Sentinel
    
    -- Consumer
    forever $ do
        val <- readChan chan
        when (val < 0) $ return ()
        putStrLn $ "Received: " ++ show val

-- | Async for high-level concurrency
asyncExample :: IO ()
asyncExample = do
    putStrLn "=== Async Examples ==="
    
    -- concurrently
    putStrLn "\n1. concurrently:"
    (result1, result2) <- concurrently 
        (threadDelay 100000 >> return "A")
        (threadDelay 100000 >> return "B")
    putStrLn $ "Results: " ++ result1 ++ ", " ++ result2
    
    -- mapConcurrently
    putStrLn "\n2. mapConcurrently:"
    results <- mapConcurrently (\x -> threadDelay 100000 >> return (x * 2)) [1..5]
    putStrLn $ "Doubled: " ++ show results
    
    -- race
    putStrLn "\n3. race:"
    result <- race 
        (threadDelay 200000 >> return "Slow")
        (threadDelay 100000 >> return "Fast")
    putStrLn $ "Winner: " ++ show result
    
    -- withAsync
    putStrLn "\n4. withAsync:"
    withAsync (threadDelay 300000 >> putStrLn "Background done") $ \a -> do
        putStrLn "Doing other work..."
        threadDelay 100000
        putStrLn "Work done"

-- | STM for atomic operations
type Account = TVar Int

withdraw :: Account -> Int -> STM Bool
withdraw acc amount = do
    balance <- readTVar acc
    if balance >= amount
        then do
            writeTVar acc (balance - amount)
            return True
        else return False

deposit :: Account -> Int -> STM ()
deposit acc amount = do
    balance <- readTVar acc
    writeTVar acc (balance + amount)

transfer :: Account -> Account -> Int -> IO ()
transfer from to amount = do
    success <- atomically $ do
        ok <- withdraw from amount
        if ok
            then do
                deposit to amount
                return True
            else return False
    if success
        then putStrLn $ "Transferred " ++ show amount
        else putStrLn "Insufficient funds"

stmExample :: IO ()
stmExample = do
    putStrLn "\n=== STM Example ==="
    acc1 <- atomically $ newTVar 1000
    acc2 <- atomically $ newTVar 500
    
    putStrLn "Before transfer:"
    b1 <- atomically $ readTVar acc1
    b2 <- atomically $ readTVar acc2
    putStrLn $ "Acc1: " ++ show b1 ++ ", Acc2: " ++ show b2
    
    transfer acc1 acc2 300
    transfer acc1 acc2 1000  -- Will fail
    
    putStrLn "After transfer:"
    b1 <- atomically $ readTVar acc1
    b2 <- atomically $ readTVar acc2
    putStrLn $ "Acc1: " ++ show b1 ++ ", Acc2: " ++ show b2

-- | Producer-Consumer with channels
producerConsumer :: IO ()
producerConsumer = do
    putStrLn "\n=== Producer-Consumer ==="
    chan <- newChan
    
    let producer = forM_ [1..10 :: Int] $ \i -> do
            writeChan chan i
            threadDelay 50000
            putStrLn $ "Produced: " ++ show i
    
    let consumer = replicateM_ 10 $ do
            val <- readChan chan
            threadDelay 70000
            putStrLn $ "Consumed: " ++ show val
    
    concurrently_ producer consumer

main :: IO ()
main = do
    putStrLn "=== Concurrency Templates ==="
    
    -- Uncomment to run examples
    -- basicThread
    -- mvarExample
    -- channelExample
    asyncExample
    stmExample
    -- producerConsumer
