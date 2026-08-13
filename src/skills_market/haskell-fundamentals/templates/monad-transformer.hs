-- Monad Transformers Template
-- For building applications with combined effects

{-# LANGUAGE FlexibleContexts #-}
{-# LANGUAGE GeneralizedNewtypeDeriving #-}

module Main where

import Control.Monad.Reader
import Control.Monad.State
import Control.Monad.IO.Class

-- Application configuration
data Config = Config
    { configName :: String
    , configDebug :: Bool
    }

-- Application state
data AppState = AppState
    { stateCounter :: Int
    , stateLogs :: [String]
    }

-- Application monad stack
newtype AppM a = AppM
    { runAppM :: ReaderT Config (StateT AppState IO) a
    } deriving (Functor, Applicative, Monad, MonadReader Config, MonadState AppState, MonadIO)

-- Run the application
runApp :: AppM a -> Config -> AppState -> IO (a, AppState)
runApp (AppM m) cfg st = runStateT (runReaderT m cfg) st

-- Example computation
exampleComputation :: AppM ()
exampleComputation = do
    -- Access configuration (Reader)
    name <- asks configName
    debug <- asks configDebug
    
    -- Modify state (State)
    modify $ \st -> st 
        { stateCounter = stateCounter st + 1
        , stateLogs = ("Running: " ++ name) : stateLogs st
        }
    
    -- IO operations
    liftIO $ putStrLn $ "Hello from " ++ name
    
    when debug $ do
        liftIO $ putStrLn "[DEBUG] Debug mode enabled"

main :: IO ()
main = do
    let config = Config "MyApp" True
    let initialState = AppState 0 []
    
    (_, finalState) <- runApp exampleComputation config initialState
    
    print finalState
