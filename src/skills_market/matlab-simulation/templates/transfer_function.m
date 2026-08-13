% MATLAB Transfer Function Analysis Template
% Usage: Modify numerator and denominator coefficients

%% Define transfer function
% G(s) = num(s) / den(s)
% Example: G(s) = (s + 1) / (s^2 + 2s + 1)

num = [1 1];           % Numerator coefficients (descending powers of s)
den = [1 2 1];         % Denominator coefficients
G = tf(num, den);

% Display transfer function
disp('Transfer Function:');
G

%% Pole-zero analysis
poles = pole(G);
zeros = zero(G);

fprintf('Poles: %s\n', mat2str(poles', 4));
fprintf('Zeros: %s\n', mat2str(zeros', 4));

%% Stability check
if all(real(poles) < 0)
    disp('System is STABLE');
else
    disp('System is UNSTABLE');
end

%% Time domain analysis
figure('Position', [100, 100, 1200, 800]);

subplot(2, 2, 1);
step(G, 'LineWidth', 2);
title('Step Response');
grid on;

subplot(2, 2, 2);
impulse(G, 'LineWidth', 2);
title('Impulse Response');
grid on;

% Step response metrics
S = stepinfo(G);
fprintf('\nStep Response Metrics:\n');
fprintf('  Rise Time: %.4f s\n', S.RiseTime);
fprintf('  Settling Time: %.4f s\n', S.SettlingTime);
fprintf('  Overshoot: %.2f %%\n', S.Overshoot);
fprintf('  Peak Time: %.4f s\n', S.PeakTime);

%% Frequency domain analysis
subplot(2, 2, 3);
bode(G, 'LineWidth', 2);
grid on;

subplot(2, 2, 4);
margin(G);
title('Bode Plot with Margins');

set(gcf, 'Color', 'w');

%% Gain and phase margins
[Gm, Pm, Wcg, Wcp] = margin(G);
fprintf('\nStability Margins:\n');
fprintf('  Gain Margin: %.2f dB at %.2f rad/s\n', 20*log10(Gm), Wcg);
fprintf('  Phase Margin: %.2f degrees at %.2f rad/s\n', Pm, Wcp);
