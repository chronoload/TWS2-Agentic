% MATLAB Neural Network Simulation Template
% Usage: Modify network structure and training data

%% Load or generate data
% Example: Use built-in dataset
[x, t] = simplefit_dataset;

% Or use your own data
% x = your_input_data;
% t = your_target_data;

%% Create feedforward neural network
hidden_neurons = 10;  % Number of neurons in hidden layer
net = feedforwardnet(hidden_neurons);

%% Configure training parameters
net.trainParam.epochs = 1000;    % Maximum epochs
net.trainParam.goal = 1e-4;      % Performance goal
net.trainParam.show = 10;        % Show progress every 10 epochs
net.divideParam.trainRatio = 0.7;
net.divideParam.valRatio = 0.15;
net.divideParam.testRatio = 0.15;

%% Train the network
fprintf('Training neural network...\n');
[net, tr] = train(net, x, t);

%% Simulate the network
y = net(x);

%% Performance evaluation
perf_mse = mse(net, x, t);
fprintf('Mean Square Error: %.6f\n', perf_mse);

% Regression analysis
[r, m, b] = regression(t, y);
fprintf('Regression R-value: %.4f\n', r);
fprintf('Regression slope: %.4f\n', m);
fprintf('Regression intercept: %.4f\n', b);

%% Visualize results
figure('Position', [100, 100, 1200, 800]);

% Network structure
subplot(2, 3, 1);
view(net);
title('Network Structure');

% Training performance
subplot(2, 3, 2);
plotperform(tr);
title('Training Performance');

% Training state
subplot(2, 3, 3);
plottrainstate(tr);
title('Training State');

% Error histogram
subplot(2, 3, 4);
e = t - y;
ploterrhist(e);
title('Error Histogram');

% Regression plot
subplot(2, 3, 5);
plotregression(t, y);
title('Regression');

% Response comparison
subplot(2, 3, 6);
plot(t, 'b-', 'LineWidth', 2);
hold on;
plot(y, 'r--', 'LineWidth', 2);
xlabel('Sample');
ylabel('Value');
legend('Target', 'Output');
title('Response Comparison');
grid on;

set(gcf, 'Color', 'w');

%% Generate Simulink model (optional)
% Uncomment to create Simulink model
% gensim(net, -1);  % -1 for continuous sampling
% open_system('model_name');

%% Save network
% save('trained_network.mat', 'net');
