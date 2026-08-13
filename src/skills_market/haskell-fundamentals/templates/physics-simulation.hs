-- Physics Simulation Template
-- Functional programming approach to physics

{-# LANGUAGE TypeSynonyms #-}

module Main where

import Text.Printf

-- Type synonyms for physics quantities
type Position = Double  -- meters
type Velocity = Double  -- m/s
type Acceleration = Double  -- m/s^2
type Time = Double  -- seconds
type Mass = Double  -- kg

-- | Kinematics: position at time t with constant acceleration
positionAt :: Position -> Velocity -> Acceleration -> Time -> Position
positionAt x0 v0 a t = x0 + v0 * t + 0.5 * a * t^2

-- | Kinematics: velocity at time t with constant acceleration
velocityAt :: Velocity -> Acceleration -> Time -> Velocity
velocityAt v0 a t = v0 + a * t

-- | Newton's second law: F = ma
force :: Mass -> Acceleration -> Double
force m a = m * a

-- | Kinetic energy: KE = 1/2 mv^2
kineticEnergy :: Mass -> Velocity -> Double
kineticEnergy m v = 0.5 * m * v^2

-- | Gravitational potential energy: PE = mgh
potentialEnergy :: Mass -> Double -> Double -> Double
potentialEnergy m g h = m * g * h

-- | Simple harmonic oscillator position
-- omega: angular frequency, x0: initial position, v0: initial velocity
shoPosition :: Double -> Position -> Velocity -> Time -> Position
shoPosition omega x0 v0 t = 
    x0 * cos (omega * t) + (v0 / omega) * sin (omega * t)

-- | Simple harmonic oscillator velocity
shoVelocity :: Double -> Position -> Velocity -> Time -> Velocity
shoVelocity omega x0 v0 t = 
    -x0 * omega * sin (omega * t) + v0 * cos (omega * t)

-- | Euler method for numerical integration
-- f: derivative function, x0: initial value, t0: start time, dt: step size
integrate :: (Double -> Double) -> Double -> Time -> Time -> [(Time, Double)]
integrate f x0 t0 dt = take 100 $ iterate step (t0, x0)
  where
    step (t, x) = (t + dt, x + dt * f x)

-- | Free fall simulation
freeFall :: Position -> Time -> [(Time, Position)]
freeFall h0 dt = 
    let g = 9.81  -- gravitational acceleration
        v t = -g * t  -- velocity function
        integratePos = integrate (\t -> -g * t) h0 0 dt
    in integratePos

-- | Print simulation results
printSimulation :: [(Time, Position)] -> IO ()
printSimulation = mapM_ printStep
  where
    printStep (t, x) = printf "t = %.2f s, x = %.2f m\n" t x

-- Example: projectile motion
projectileExample :: IO ()
projectileExample = do
    putStrLn "Projectile Motion Simulation:"
    putStrLn "Initial height: 100 m"
    putStrLn "Time step: 0.1 s"
    putStrLn "---------------------------"
    let sim = freeFall 100 0.1
    printSimulation $ take 15 sim

main :: IO ()
main = projectileExample
