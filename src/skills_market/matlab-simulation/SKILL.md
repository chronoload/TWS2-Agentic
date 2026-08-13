---
name: matlab-simulation
description: MATLAB and Simulink programming for system modeling, control design, and dynamic system simulation
---

# MATLAB & Simulink Simulation Skill

## Overview
Provides MATLAB/Simulink programming capabilities for modeling and simulating dynamic systems, control systems, neural networks, and engineering simulations.

## Reference
Based on《MATLAB/Simulink 系统仿真超级学习手册》and standard MATLAB/Simulink simulation practices.

## When to Use
Trigger this skill when the user requests:
- MATLAB/Simulink simulation or modeling
- Dynamic system simulation
- Control system design
- ODE solving and differential equations
- Monte Carlo simulation
- System response analysis

## Core Capabilities

### 1. ODE Solvers (Dynamic Systems)
```matlab
% Define ODE system
dydt = @(t,y) [y(2); -sin(y(1))];  % Pendulum equation

% Solve with ode45 (Runge-Kutta)
[t, y] = ode45(dydt, [0 10], [pi/4; 0]);

% Other solvers
[t, y] = ode15s(dydt, [0 10], y0);   % Stiff systems
[t, y] = ode23(dydt, [0 10], y0);    % Lower accuracy, faster
[t, y] = ode113(dydt, [0 10], y0);   % Variable order

% With options
options = odeset('RelTol', 1e-6, 'AbsTol', 1e-8);
[t, y] = ode45(dydt, [0 10], y0, options);
```

### 2. Transfer Functions & State-Space
```matlab
% Transfer function: G(s) = (s+1)/(s^2 + 2s + 1)
num = [1 1];
den = [1 2 1];
G = tf(num, den);

% State-space: dx/dt = Ax + Bu, y = Cx + Du
A = [0 1; -1 -2];
B = [0; 1];
C = [1 0];
D = 0;
sys = ss(A, B, C, D);

% Convert between forms
G_ss = ss(G);
G_tf = tf(sys);

% Poles and zeros
p = pole(G);
z = zero(G);
```

### 3. Time Response Analysis
```matlab
% Step response
figure;
step(G);
title('Step Response');

% Impulse response
impulse(G);

% Initial condition response
initial(sys, x0);

% Arbitrary input response
t = 0:0.01:10;
u = sin(t);
lsim(G, u, t);

% Extract response data
[y, t] = step(G);
stepinfo(G);  % Rise time, settling time, overshoot
```

### 4. Frequency Response Analysis
```matlab
% Bode plot
figure;
bode(G);
grid on;

% Nyquist plot
nyquist(G);

% Nichols chart
nichols(G);

% Gain and phase margins
[Gm, Pm, Wcg, Wcp] = margin(G);

% Bandwidth
bw = bandwidth(G);
```

### 5. Root Locus
```matlab
% Root locus plot
figure;
rlocus(G);
title('Root Locus');

% Find gain for specific damping
[k, poles] = rlocfind(G);

% S-grid (damping ratio lines)
sgrid(0.5, 0);  % zeta=0.5
```

### 6. Simulink Programmatic Simulation
```matlab
% Open model
open_system('model_name.slx');

% Set parameters
set_param('model_name/Block', 'Gain', '10');

% Run simulation
simOut = sim('model_name', 'StopTime', '10');

% Access simulation data
time = simOut.tout;
output = simOut.yout.signals.values;

% Batch simulation with parameter sweep
for k = 1:5
    set_param('model_name/Gain', 'Gain', num2str(k));
    simOut = sim('model_name');
    results(k) = max(simOut.yout);
end
```

### 7. Monte Carlo Simulation
```matlab
% Monte Carlo for uncertainty analysis
N = 1000;
results = zeros(N, 1);

for i = 1:N
    % Random parameter variation
    param = nominal_value * (1 + 0.1*randn);
    
    % Run simulation
    [t, y] = ode45(@(t,y) sim_func(y, param), [0 10], y0);
    
    % Store result
    results(i) = max(y);
end

% Analyze results
mean_result = mean(results);
std_result = std(results);
histogram(results, 50);
```

### 8. Control System Design
```matlab
% PID controller tuning
C = pidtune(G, 'PID');

% Lead-lag compensator
% Gc(s) = K * (s+z)/(s+p)
K = 10; z = 1; p = 5;
Gc = tf(K*[1 z], [1 p]);

% Closed-loop system
Gcl = feedback(Gc*G, 1);

% Stability analysis
isStable = all(real(pole(Gcl)) < 0);

% Bode plot with margins
figure;
margin(Gc*G);
```

### 9. State-Space Analysis
```matlab
% Controllability and observability
Co = ctrb(A, B);
Ob = obsv(A, C);

rank_Co = rank(Co);  % Should be n for controllable
rank_Ob = rank(Ob);  % Should be n for observable

% Eigenvalues and eigenvectors
[V, D] = eig(A);

% State feedback design
K = place(A, B, desired_poles);
Acl = A - B*K;  % Closed-loop A matrix
```

### 10. Simulation Data Visualization
```matlab
% Multiple response comparison
figure;
step(G1, 'b', G2, 'r--', G3, 'g-.');
legend('System 1', 'System 2', 'System 3');
grid on;

% Subplots for multiple views
figure;
subplot(2,1,1);
plot(t, y(:,1));
ylabel('Position');
subplot(2,1,2);
plot(t, y(:,2));
ylabel('Velocity');
xlabel('Time');

% 3D phase portrait
figure;
plot3(y(:,1), y(:,2), y(:,3));
xlabel('x_1'); ylabel('x_2'); zlabel('x_3');
```

### 11. Neural Network Simulation
```matlab
% Create feedforward neural network
net = feedforwardnet(10);  % 10 neurons in hidden layer

% Train network
[net, tr] = train(net, x, t);

% Simulate network
y = net(x);

% Performance evaluation
perf_mse = mse(net, x, t);
[r, m, b] = regression(t, y);

% Generate Simulink model from trained network
gensim(net, -1);  % -1 for continuous sampling

% Plot training results
figure;
plotperform(tr);
figure;
plotregression(t, y);
```

### 12. Simulink Module Libraries Reference
```
% Standard Simulink Libraries:
% - Continuous: Integrator, Derivative, Transfer Fcn, State-Space
% - Discrete: Unit Delay, Zero-Order Hold, Discrete Transfer Fcn
% - Discontinuities: Saturation, Relay, Backlash, Dead Zone
% - Math Operations: Gain, Sum, Product, Trigonometric Function
% - Signal Routing: Mux, Demux, Selector, Switch
% - Sinks: Scope, To Workspace, Display, XY Graph
% - Sources: Step, Sine Wave, Ramp, Random Number
% - Ports & Subsystems: Subsystem, Enabled Subsystem, Triggered Subsystem
```

## Bundled Resources

### Templates
- `templates/ode_simulation.m` - ODE solver template
- `templates/transfer_function.m` - Transfer function analysis
- `templates/state_space.m` - State-space analysis
- `templates/simulink_batch.m` - Simulink batch simulation
- `templates/monte_carlo.m` - Monte Carlo simulation

### Usage Example
```matlab
% Complete control system simulation workflow

% 1. Define plant
G = tf(1, [1 2 1]);

% 2. Design controller
C = pidtune(G, 'PID');

% 3. Analyze open-loop
figure;
margin(C*G);

% 4. Closed-loop simulation
Gcl = feedback(C*G, 1);
figure;
step(Gcl);
title('Closed-loop Step Response');

% 5. Extract performance metrics
S = stepinfo(Gcl);
fprintf('Rise time: %.4f s\n', S.RiseTime);
fprintf('Overshoot: %.2f %%\n', S.Overshoot);
```
