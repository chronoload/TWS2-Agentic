-- Lens Template
-- Working with lenses and optics

{-# LANGUAGE TemplateHaskell #-}
{-# LANGUAGE RankNTypes #-}

module Main where

import Control.Lens

-- | Simple record with generated lenses
data Person = Person
    { _name    :: String
    , _age     :: Int
    , _address :: Address
    } deriving (Show, Eq)

data Address = Address
    { _street  :: String
    , _city    :: String
    , _country :: String
    } deriving (Show, Eq)

-- Generate lenses
makeLenses ''Person
makeLenses ''Address

-- | Manual lens definition example
nameLens :: Lens' Person String
nameLens f (Person n a addr) = fmap (\n' -> Person n' a addr) (f n)

-- | Example data
alice :: Person
alice = Person "Alice" 30 (Address "123 Main St" "New York" "USA")

bob :: Person
bob = Person "Bob" 25 (Address "456 Oak Ave" "Los Angeles" "USA")

-- | Using lenses
main :: IO ()
main = do
    putStrLn "=== Lens Examples ==="
    
    -- View (get)
    putStrLn $ "\n1. View:"
    putStrLn $ "Alice's name: " ++ view name alice
    putStrLn $ "Alice's city: " ++ alice ^. address . city
    
    -- Set
    putStrLn $ "\n2. Set:"
    let aliceInLondon = alice & address . city .~ "London"
    putStrLn $ "Alice moved to: " ++ aliceInLondon ^. address . city
    
    -- Modify
    putStrLn $ "\n3. Modify:"
    let birthdayAlice = alice & age +~ 1
    putStrLn $ "After birthday: " ++ show (birthdayAlice ^. age)
    
    let doubleAge = alice & age %~ (*2)
    putStrLn $ "Double age: " ++ show (doubleAge ^. age)
    
    -- Multiple updates
    putStrLn $ "\n4. Multiple updates:"
    let updated = alice 
            & name .~ "Alicia"
            & age +~ 5
            & address . city .~ "Paris"
        in print updated
    
    -- Traversal
    putStrLn $ "\n5. Traversal:"
    let people = [alice, bob]
    let names = people ^.. traverse . name
    putStrLn $ "All names: " ++ show names
    
    let agedPeople = people ^.. traverse . filtered (\p -> p ^. age >= 30)
    putStrLn $ "People 30+: " ++ show (length agedPeople)
    
    -- Fold
    putStrLn $ "\n6. Fold:"
    let totalAge = sumOf (traverse . age) people
    putStrLn $ "Total age: " ++ show totalAge
    
    let avgAge = totalAge `div` length people
    putStrLn $ "Average age: " ++ show avgAge
    
    -- Predicate operations
    putStrLn $ "\n7. Predicates:"
    let hasAlice = anyOf (traverse . name) (== "Alice") people
    putStrLn $ "Has Alice: " ++ show hasAlice
    
    -- Setter with function
    putStrLn $ "\n8. Setter with function:"
    let uppercased = people & traverse . name %~ map toUpper
    print uppercased
    
    -- Review (constructor)
    putStrLn $ "\n9. Review:"
    let newPerson = _Person # ("Charlie" :: String, 35 :: Int, Address "789 Pine St" "Chicago" "USA" :: Address)
    print newPerson

-- | Helper function
toUpper :: String -> String
toUpper = map (\c -> if c >= 'a' && c <= 'z' then toEnum (fromEnum c - 32) else c)

-- | Filter helper
filtered :: (a -> Bool) -> Traversal' a a
filtered p f a | p a       = f a a
               | otherwise = pure a
