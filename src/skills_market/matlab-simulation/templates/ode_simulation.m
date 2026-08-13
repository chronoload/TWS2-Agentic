% MATLAB ODE Simulation Template
% Usage: Modify the ODE function and initial conditions

%% Define the ODE system
% dy/dt = f(t, y)
% Example: Simple pendulum: d²θ/dt² + sin(θ) = 0
ode_func = @(t, y) [y(2); -sin(y(1))];

%% Simulation parameters
tspan = [0 10];      % Time interval [t0 tf]
y0 = [pi/4; 0];      % Initial conditions [theta; d_theta/dt]

%% Solve ODE
% Choose solver based on problem type:
% - ode45: General purpose (Runge-Kutta), non-stiff
% - ode15s: Stiff systems
% - ode23: Lower accuracy, faster
% - ode113: Variable order, high accuracy

options = odeset('RelTol', 1e-6, 'AbsTol', 1e-8);
[t, y] = ode45(ode_func, tspan, y0, options);

%% Visualize results
figure('Position', [100, 100, 1000, 600]);

subplot(1, 2, 1);
plot(t, y(:,1), 'b-', 'LineWidth', 2);
xlabel('Time (s)');
ylabel('Angle (rad)');
title('Pendulum Angle vs Time');
grid on;

subplot(1, 2, 2);
plot(y(:,1), y(:,2), 'r-', 'LineWidth', 2);
xlabel('Angle (rad)');
ylabel('Angular Velocity (rad/s)');
title('Phase Portrait');
grid on;

set(gcf, 'Color', 'w');

%% For stiff systems, use ode15s
% [t, y] = ode15s(ode_func, tspan, y0, options);
