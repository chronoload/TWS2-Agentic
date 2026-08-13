-- Basic Haskell Template
-- A starting point for Haskell projects

module Main where

import System.IO

-- | Main entry point
main :: IO ()
main = do
    hSetBuffering stdout NoBuffering
    putStrLn "Hello, Haskell!"
    -- Add your code here

-- | Pure function example
add :: Int -> Int -> Int
add a b = a + b

-- | Pattern matching example
factorial :: Integer -> Integer
factorial 0 = 1
factorial n = n * factorial (n - 1)

-- | Higher-order function example
processList :: [Int] -> [Int]
processList = map (*2) . filter even
