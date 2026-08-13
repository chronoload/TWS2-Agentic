-- Web Application Template (Snap Framework)
-- A basic web application structure

{-# LANGUAGE OverloadedStrings #-}

module Main where

import Snap.Core
import Snap.Http.Server
import Snap.Util.FileServe
import Data.Text (Text)
import qualified Data.Text as T

-- | Simple handler
helloHandler :: Handler ()
helloHandler = writeText "Hello, World!"

-- | Handler with route parameter
greetHandler :: Handler ()
greetHandler = do
    mname <- getParam "name"
    case mname of
        Just name -> writeText $ "Hello, " <> name <> "!"
        Nothing   -> writeText "Hello, stranger!"

-- | JSON response (requires aeson)
jsonHandler :: Handler ()
jsonHandler = do
    modifyResponse $ setContentType "application/json"
    writeText "{\"message\": \"Hello from Snap!\"}"

-- | Form handler
formHandler :: Handler ()
formHandler = do
    mAction <- getParam "action"
    case mAction of
        Just "submit" -> do
            mValue <- getParam "value"
            case mValue of
                Just v -> writeText $ "Received: " <> v
                Nothing -> writeText "No value provided"
        _ -> writeText "<form method='POST'><input name='value'/><button>Submit</button></form>"

-- | File serving handler
staticHandler :: Handler ()
staticHandler = serveDirectory "static"

-- | Main site router
site :: Snap ()
site = 
    ifTop helloHandler
    <|> route [("/greet", greetHandler)]
    <|> route [("/api/json", jsonHandler)]
    <|> route [("/form", formHandler)]
    <|> route [("/static", staticHandler)]

-- | Configuration
config :: Config Snap Snap
config = setPort 8000 $ 
         setBind "127.0.0.1" $ 
         defaultConfig

-- | Main entry point
main :: IO ()
main = httpServe config site
