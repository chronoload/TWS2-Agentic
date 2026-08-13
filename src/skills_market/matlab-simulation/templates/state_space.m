% MATLAB State-Space Analysis Template
% Usage: Modify A, B, C, D matrices

%% Define state-space system
% dx/dt = A*x + B*u
% y = C*x + D*u

% Example: Mass-spring-damper system
m = 1; c = 2; k = 1;

A = [0 1; -k/m -c/m];
B = [0; 1/m];
C = [1 0];    % Output is position
D = 0;

sys = ss(A, B, C, D);

disp('State-Space System:');
sys

%% Convert to transfer function
G = tf(sys);
disp('Equivalent Transfer Function:');
G

%% Eigenvalue analysis
[V, D_eig] = eig(A);
eigenvalues = diag(D_eig);

fprintf('Eigenvalues: %s\n', mat2str(eigenvalues', 4));

if all(real(eigenvalues) < 0)
    disp('System is STABLE');
else
    disp('System is UNSTABLE');
end

%% Controllability and Observability
Co = ctrb(A, B);
Ob = obsv(A, C);

rank_Co = rank(Co);
rank_Ob = rank(Ob);
n = size(A, 1);

fprintf('\nControllability: rank = %d/%d - %s\n', ...
    rank_Co, n, ternary(rank_Co==n, 'CONTROLLABLE', 'NOT CONTROLLABLE'));
fprintf('Observability: rank = %d/%d - %s\n', ...
    rank_Ob, n, ternary(rank_Ob==n, 'OBSERVABLE', 'NOT OBSERVABLE'));

%% Time response
figure('Position', [100, 100, 1200, 500]);

subplot(1, 3, 1);
step(sys, 'LineWidth', 2);
title('Step Response');
grid on;

subplot(1, 3, 2);
impulse(sys, 'LineWidth', 2);
title('Impulse Response');
grid on;

%% Initial condition response
x0 = [1; 0];  % Initial state
subplot(1, 3, 3);
initial(sys, x0);
title('Initial Condition Response');
grid on;

set(gcf, 'Color', 'w');

%% State feedback design (pole placement)
% Desired closed-loop poles
desired_poles = [-2+2i, -2-2i];

% Calculate feedback gain
K = place(A, B, desired_poles);

fprintf('\nState Feedback Gain: K = %s\n', mat2str(K, 4));

% Closed-loop system
Acl = A - B*K;
sys_cl = ss(Acl, B, C, D);

fprintf('Closed-loop poles: %s\n', mat2str(eig(Acl)', 4));

%% Helper function (for older MATLAB versions without ternary)
function result = ternary(condition, trueVal, falseVal)
    if condition
        result = trueVal;
    else
        result = falseVal;
    end
end
