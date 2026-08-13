% MATLAB Monte Carlo Simulation Template
% Usage: Modify simulation function and uncertainty parameters

%% Configuration
N = 1000;                    % Number of Monte Carlo iterations
nominal_params = struct('K', 10, 'zeta', 0.5, 'wn', 2);  % Nominal parameters
uncertainty = 0.1;           % ±10% variation

%% Preallocate results
results = zeros(N, 1);
rise_times = zeros(N, 1);
overshoots = zeros(N, 1);
settling_times = zeros(N, 1);

fprintf('Starting Monte Carlo simulation (%d iterations)...\n', N);

%% Monte Carlo loop
for i = 1:N
    % Generate random parameters (normal distribution)
    K = nominal_params.K * (1 + uncertainty * randn);
    zeta = nominal_params.zeta * (1 + uncertainty * randn);
    wn = nominal_params.wn * (1 + uncertainty * randn);
    
    % Ensure physical constraints
    K = max(K, 0.1);
    zeta = max(zeta, 0.01);
    wn = max(wn, 0.1);
    
    % Run simulation (replace with your simulation function)
    % Example: Second-order system step response
    num = [K * wn^2];
    den = [1, 2*zeta*wn, wn^2];
    G = tf(num, den);
    
    % Get step response
    [y, t] = step(G);
    
    % Store peak value
    results(i) = max(y);
    
    % Get performance metrics
    S = stepinfo(G);
    rise_times(i) = S.RiseTime;
    overshoots(i) = S.Overshoot;
    settling_times(i) = S.SettlingTime;
    
    % Progress indicator
    if mod(i, 100) == 0
        fprintf('  Completed %d/%d iterations\n', i, N);
    end
end

fprintf('Monte Carlo simulation complete!\n\n');

%% Statistical Analysis
fprintf('=== Statistical Results ===\n');
fprintf('Peak Value:\n');
fprintf('  Mean: %.4f, Std: %.4f\n', mean(results), std(results));
fprintf('  Min: %.4f, Max: %.4f\n', min(results), max(results));

fprintf('\nRise Time:\n');
fprintf('  Mean: %.4f, Std: %.4f\n', mean(rise_times), std(rise_times));

fprintf('\nOvershoot:\n');
fprintf('  Mean: %.2f%%, Std: %.2f%%\n', mean(overshoots), std(overshoots));

%% Visualize Results
figure('Position', [100, 100, 1200, 800]);

% Histogram of peak values
subplot(2, 2, 1);
histogram(results, 50, 'FaceColor', [0.2 0.6 0.8], 'EdgeColor', 'none');
hold on;
xline(mean(results), 'r-', 'LineWidth', 2);
xlabel('Peak Value');
ylabel('Frequency');
title('Distribution of Peak Values');
grid on;

% Histogram of rise times
subplot(2, 2, 2);
histogram(rise_times, 50, 'FaceColor', [0.8 0.4 0.2], 'EdgeColor', 'none');
hold on;
xline(mean(rise_times), 'r-', 'LineWidth', 2);
xlabel('Rise Time (s)');
ylabel('Frequency');
title('Distribution of Rise Times');
grid on;

% Histogram of overshoots
subplot(2, 2, 3);
histogram(overshoots, 50, 'FaceColor', [0.3 0.7 0.3], 'EdgeColor', 'none');
hold on;
xline(mean(overshoots), 'r-', 'LineWidth', 2);
xlabel('Overshoot (%)');
ylabel('Frequency');
title('Distribution of Overshoot');
grid on;

% Cumulative distribution
subplot(2, 2, 4);
[cdf_x, cdf_y] = ecdf(results);
plot(cdf_x, cdf_y, 'b-', 'LineWidth', 2);
grid on;
xlabel('Peak Value');
ylabel('Cumulative Probability');
title('Cumulative Distribution Function');

set(gcf, 'Color', 'w');

%% Confidence intervals
ci_95 = prctile(results, [2.5, 97.5]);
fprintf('\n95%% Confidence Interval for Peak Value: [%.4f, %.4f]\n', ci_95(1), ci_95(2));

%% Save results
% save('monte_carlo_results.mat', 'results', 'rise_times', 'overshoots', 'settling_times');
