% MATLAB Simulink Batch Simulation Template
% Usage: Modify model name and parameter sweep values

%% Configuration
model_name = 'my_model';  % Change to your model name
param_name = 'K';         % Parameter to sweep
param_values = [1, 2, 5, 10, 20];  % Values to test

%% Open model (if not already open)
% open_system([model_name '.slx']);

%% Preallocate results
N = length(param_values);
results = struct();
results.param = param_values;
results.overshoot = zeros(N, 1);
results.settling_time = zeros(N, 1);
results.peak_time = zeros(N, 1);
results.sim_time = cell(N, 1);
results.sim_output = cell(N, 1);

%% Batch simulation loop
fprintf('Starting batch simulation...\n');
fprintf('Parameter: %s, Values: %s\n\n', param_name, mat2str(param_values));

for i = 1:N
    % Set parameter value
    set_param([model_name '/' param_name], 'Gain', num2str(param_values(i)));
    
    fprintf('Running simulation %d/%d (K = %.2f)...\n', i, N, param_values(i));
    
    % Run simulation
    simOut = sim(model_name, 'StopTime', '10');
    
    % Extract output (adjust variable names based on your model)
    time = simOut.tout;
    output = simOut.yout.signals.values;
    
    results.sim_time{i} = time;
    results.sim_output{i} = output;
    
    % Calculate performance metrics (if step response)
    step_data = iddata(output, time, 0);
    step_info = stepinfo(step_data);
    
    results.overshoot(i) = step_info.Overshoot;
    results.settling_time(i) = step_info.SettlingTime;
    results.peak_time(i) = step_info.PeakTime;
end

fprintf('\nBatch simulation complete!\n');

%% Visualize results
figure('Position', [100, 100, 1200, 600]);

% Plot all responses
subplot(2, 2, 1);
hold on;
for i = 1:N
    plot(results.sim_time{i}, results.sim_output{i}, 'LineWidth', 2);
end
xlabel('Time (s)');
ylabel('Output');
title('Step Responses for Different K Values');
legend(string(param_values));
grid on;

% Overshoot vs Parameter
subplot(2, 2, 2);
plot(param_values, results.overshoot, 'bo-', 'LineWidth', 2, 'MarkerSize', 8);
xlabel(param_name);
ylabel('Overshoot (%)');
title('Overshoot vs Parameter');
grid on;

% Settling Time vs Parameter
subplot(2, 2, 3);
plot(param_values, results.settling_time, 'rs-', 'LineWidth', 2, 'MarkerSize', 8);
xlabel(param_name);
ylabel('Settling Time (s)');
title('Settling Time vs Parameter');
grid on;

% Peak Time vs Parameter
subplot(2, 2, 4);
plot(param_values, results.peak_time, 'g^-', 'LineWidth', 2, 'MarkerSize', 8);
xlabel(param_name);
ylabel('Peak Time (s)');
title('Peak Time vs Parameter');
grid on;

set(gcf, 'Color', 'w');

%% Save results
% save('batch_simulation_results.mat', 'results');
fprintf('Results saved to workspace variable ''results''\n');
