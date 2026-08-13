-- Database Template (Persistent)
-- Type-safe database access

{-# LANGUAGE GADTs #-}
{-# LANGUAGE GeneralizedNewtypeDeriving #-}
{-# LANGUAGE OverloadedStrings #-}
{-# LANGUAGE QuasiQuotes #-}
{-# LANGUAGE TemplateHaskell #-}
{-# LANGUAGE TypeFamilies #-}

module Main where

import Database.Persist
import Database.Persist.Sqlite
import Database.Persist.TH
import Control.Monad.IO.Class (liftIO)

-- Define database models
share [mkPersist sqlSettings, mkMigrate "migrateAll"] [persistLowerCase|
-- User entity
User
    name String
    email String
    age Int Maybe
    deriving Show

-- Post entity
Post
    title String
    content Text
    authorId UserId
    published Bool
    deriving Show

-- Comment entity
Comment
    postId PostId
    userId UserId
    content Text
    deriving Show
|]

-- | Create initial data
initDB :: IO ()
initDB = runSqlite ":memory:" $ do
    runMigration migrateAll
    
    -- Insert users
    userId1 <- insert $ User "Alice" "alice@example.com" (Just 25)
    userId2 <- insert $ User "Bob" "bob@example.com" (Just 30)
    
    -- Insert posts
    postId1 <- insert $ Post "First Post" "Hello World!" userId1 True
    postId2 <- insert $ Post "Second Post" "Another post" userId1 False
    
    -- Insert comments
    _ <- insert $ Comment postId1 userId2 "Great post!"
    
    liftIO $ putStrLn "Database initialized!"

-- | Query examples
queryExamples :: SqlPersistM ()
queryExamples = do
    -- Get all users
    users <- selectList ([] :: [Filter User]) []
    liftIO $ putStrLn $ "All users: " ++ show (length users)
    
    -- Get users by age
    olderUsers <- selectList [UserAge >. Just 25] []
    liftIO $ putStrLn $ "Users over 25: " ++ show (length olderUsers)
    
    -- Get user by email
    maybeUser <- getBy $ UniqueUserEmail "alice@example.com"
    case maybeUser of
        Just (Entity userId user) -> do
            liftIO $ putStrLn $ "Found Alice with ID: " ++ show userId
            -- Get user's posts
            posts <- selectList [PostAuthorId ==. userId] []
            liftIO $ putStrLn $ "Alice has " ++ show (length posts) ++ " posts"
        Nothing -> liftIO $ putStrLn "Alice not found"
    
    -- Join query: get posts with authors
    results <- selectList ([] :: [Filter Post]) []
    mapM_ (\(Entity postId post) -> do
        author <- get (postAuthorId post)
        liftIO $ putStrLn $ "Post: " ++ T.unpack (postTitle post) ++ 
                           " by " ++ maybe "Unknown" userName author
        ) results

-- | Update examples
updateExamples :: SqlPersistM ()
updateExamples = do
    -- Find and update
    users <- selectList ([] :: [Filter User]) []
    case users of
        (Entity userId _ : _) -> do
            set userId [UserName =. "Updated Name"]
            liftIO $ putStrLn "Updated first user's name"
        [] -> return ()
    
    -- Delete unpublished posts
    deleted <- deleteByWhere ([] :: [Filter Post])
    liftIO $ putStrLn $ "Deleted posts"

-- | Main function
main :: IO ()
main = runSqlite ":memory:" $ do
    runMigration migrateAll
    queryExamples
    updateExamples
