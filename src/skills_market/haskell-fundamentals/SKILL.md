---
name: haskell-fundamentals
description: Haskell functional programming expertise including type system, monads, functors, applicatives, and practical application development
---

# Haskell Fundamentals Skill

## Overview
Provides comprehensive Haskell functional programming capabilities based on:
- **Haskell Cookbook** (Yogesh Sajanikar, 2017)
- **Haskell Design Patterns** (Ryan Lemmer, 2015)
- **Haskell in Depth** (Vitaly Bragilevsky, 2021)
- **Learn Physics with Functional Programming** (Scott N. Walck, 2023)

## When to Use
Trigger this skill when the user requests:
- Haskell code development or debugging
- Functional programming concepts (monads, functors, applicatives)
- Type system questions (GADTs, type families, data kinds)
- Haskell application development (web, database, concurrency)
- Physics simulation with functional programming

## Core Capabilities

### 1. Environment Setup
```bash
# Install Stack (recommended)
# Windows: chocolatey install haskell-stack
# macOS: brew install haskell-stack

# Create and build project
stack new myproject
stack build
stack exec myproject
stack ghci
```

### 2. Basic Haskell Patterns
```haskell
-- Pure function
add :: Int -> Int -> Int
add a b = a + b

-- Pattern matching
factorial :: Integer -> Integer
factorial 0 = 1
factorial n = n * factorial (n - 1)

-- Higher-order functions
evens :: [Int] -> [Int]
evens = filter even

-- Function composition
result = f . g $ x
```

### 3. Type System
```haskell
-- Algebraic Data Types
data Shape = Circle Double | Rectangle Double Double

-- Maybe for optional values
safeDivide :: Double -> Double -> Maybe Double
safeDivide _ 0 = Nothing
safeDivide x y = Just (x / y)

-- Either for error handling
safeRead :: String -> Either String Int
safeRead s = case reads s of
    [(x, "")] -> Right x
    _         -> Left "Parse failed"
```

### 4. Functors, Applicatives, Monads
```haskell
-- Functor: fmap
fmap (+1) (Just 5)  -- Just 6
fmap (+1) [1,2,3]   -- [2,3,4]

-- Applicative: pure and <*>
pure (+) <*> Just 1 <*> Just 2  -- Just 3

-- Monad: bind (>>=)
Just 5 >>= \x -> Just (x + 1)  -- Just 6

-- Common monads: Maybe, Either, Reader, State, Writer, IO
```

### 5. Common Type Classes
```haskell
-- Eq, Ord, Show, Read, Num
data Color = Red | Green | Blue
    deriving (Eq, Show, Read)

-- Functor, Applicative, Monad
instance Functor Maybe where
    fmap _ Nothing  = Nothing
    fmap f (Just x) = Just (f x)
```

### 6. Data Structures
```haskell
import qualified Data.Map as Map
import qualified Data.Set as Set
import qualified Data.Text as T
import qualified Data.Vector as V

-- Map operations
Map.insert "key" value map
Map.lookup "key" map

-- Efficient text
T.pack :: String -> Text
T.splitOn "," text
```

### 7. I/O Patterns
```haskell
-- Basic I/O
main :: IO ()
main = do
    putStrLn "Enter name:"
    name <- getLine
    putStrLn $ "Hello, " ++ name

-- Resource management with bracket
bracket :: IO a -> (a -> IO b) -> (a -> IO c) -> IO c
```

### 8. Monad Transformers
```haskell
import Control.Monad.Reader
import Control.Monad.State

type AppM = ReaderT Config (StateT AppState IO)

runApp :: AppM a -> Config -> AppState -> IO (a, AppState)
runApp app cfg st = runStateT (runReaderT app cfg) st
```

### 9. Concurrent Programming
```haskell
import Control.Concurrent
import Control.Concurrent.STM
import Control.Concurrent.Async

-- Fork thread
forkIO :: IO () -> IO ThreadId

-- STM for thread-safe state
transfer :: Account -> Account -> Int -> IO ()
transfer from to amount = atomically $ do
    withdraw from amount
    deposit to amount

-- High-level concurrency
concurrently :: IO a -> IO b -> IO (a, b)
```

### 10. Parser Combinators
```haskell
import Text.Parsec

expr :: Parser Int
expr = chainl1 term addOp

addOp :: Parser (Int -> Int -> Int)
addOp = char '+' >> return (+)
     <|> char '-' >> return (-)
```

### 11. Testing
```haskell
-- QuickCheck property testing
import Test.QuickCheck

prop_reverseInverse :: [Int] -> Bool
prop_reverseInverse xs = reverse (reverse xs) == xs

-- Run: quickCheck prop_reverseInverse
```

### 12. Physics Simulation (Functional)
```haskell
-- Kinematics
positionAt :: Double -> Double -> Double -> Double -> Double
positionAt x0 v0 a t = x0 + v0 * t + 0.5 * a * t^2

-- Simple harmonic oscillator
shoPosition :: Double -> Double -> Double -> Double -> Double
shoPosition omega x0 v0 t = 
    x0 * cos (omega * t) + (v0 / omega) * sin (omega * t)
```

## Quick Reference

### GHC Extensions
```haskell
{-# LANGUAGE OverloadedStrings #-}
{-# LANGUAGE DeriveGeneric #-}
{-# LANGUAGE GADTs #-}
{-# LANGUAGE TypeFamilies #-}
{-# LANGUAGE DataKinds #-}
{-# LANGUAGE RankNTypes #-}
```

### GHCi Commands
```
:load file.hs    -- Load file
:reload          -- Reload
:type expr       -- Check type
:info Name       -- Show info
```

### Common Libraries
- **base** - Standard library
- **text/containers/vector** - Data structures
- **lens** - Lenses and optics
- **mtl/transformers** - Monad transformers
- **aeson** - JSON
- **parsec/attoparsec** - Parsing
- **quickcheck/tasty** - Testing
- **snap/servant** - Web frameworks
