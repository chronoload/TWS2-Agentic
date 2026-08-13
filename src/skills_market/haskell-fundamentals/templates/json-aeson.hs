-- JSON Processing Template (Aeson)
-- Working with JSON data

{-# LANGUAGE DeriveGeneric #-}
{-# LANGUAGE OverloadedStrings #-}

module Main where

import Data.Aeson
import Data.Aeson.Types
import GHC.Generics (Generic)
import qualified Data.Text as T
import qualified Data.ByteString.Lazy as B

-- | Simple data type with automatic JSON instances
data Person = Person
    { personName :: String
    , personAge  :: Int
    , personEmail :: Maybe String
    } deriving (Show, Generic, Eq)

instance ToJSON Person
instance FromJSON Person

-- | Custom JSON instance with field renaming
data Product = Product
    { productId   :: Int
    , productName :: String
    , productPrice :: Double
    } deriving (Show, Eq)

instance ToJSON Product where
    toJSON (Product pId pName pPrice) =
        object [ "id"    .= pId
               , "name"  .= pName
               , "price" .= pPrice
               ]

instance FromJSON Product where
    parseJSON = withObject "Product" $ \v -> Product
        <$> v .: "id"
        <*> v .: "name"
        <*> v .: "price"

-- | Nested data structures
data Address = Address
    { street  :: String
    , city    :: String
    , country :: String
    } deriving (Show, Generic)

instance ToJSON Address
instance FromJSON Address

data Company = Company
    { companyName    :: String
    , companyAddress :: Address
    , companyEmployees :: Int
    } deriving (Show, Generic)

instance ToJSON Company
instance FromJSON Company

-- | Sum types with JSON
data Shape 
    = Circle { radius :: Double }
    | Rectangle { width :: Double, height :: Double }
    | Triangle { a :: Double, b :: Double, c :: Double }
    deriving (Show, Eq)

instance ToJSON Shape where
    toJSON (Circle r) = object ["type" .= ("Circle" :: String), "radius" .= r]
    toJSON (Rectangle w h) = object ["type" .= ("Rectangle" :: String), "width" .= w, "height" .= h]
    toJSON (Triangle a b c) = object ["type" .= ("Triangle" :: String), "a" .= a, "b" .= b, "c" .= c]

instance FromJSON Shape where
    parseJSON = withObject "Shape" $ \v -> do
        shapeType <- v .: "type"
        case shapeType of
            ("Circle" :: String) -> Circle <$> v .: "radius"
            ("Rectangle" :: String) -> Rectangle <$> v .: "width" <*> v .: "height"
            ("Triangle" :: String) -> Triangle <$> v .: "a" <*> v .: "b" <*> v .: "c"
            _ -> fail "Unknown shape type"

-- | Working with JSON
main :: IO ()
main = do
    -- Encoding
    let person = Person "Alice" 30 (Just "alice@example.com")
    let personJSON = encode person
    B.putStrLn personJSON
    
    -- Decoding
    let result = decode personJSON :: Maybe Person
    case result of
        Just p -> putStrLn $ "Decoded: " ++ show p
        Nothing -> putStrLn "Failed to decode"
    
    -- Working with objects
    let json = object [ "name" .= ("Bob" :: String)
                      , "age"  .= (25 :: Int)
                      ]
    let name = json .: "name" :: Parser String
    case name of
        Success n -> putStrLn $ "Name: " ++ n
        Error e -> putStrLn $ "Error: " ++ e
    
    -- Nested access
    let company = Company "Acme" (Address "123 Main St" "NYC" "USA") 100
    let companyJSON = encode company
    B.putStrLn companyJSON
    
    -- Array of objects
    let people = [Person "Alice" 30 Nothing, Person "Bob" 25 Nothing]
    let peopleJSON = encode people
    B.putStrLn peopleJSON
    
    -- Pretty printing
    putStrLn $ "Pretty: " ++ show (encode person)
