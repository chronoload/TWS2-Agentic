% MATLAB 2D Plotting Template
% Usage: Replace x, y with your data variables

%% Prepare data
x = 1:10;
y = x.^2;

%% Create figure
figure('Position', [100, 100, 800, 600]);

%% Plot
plot(x, y, 'b-', 'LineWidth', 2);
hold on;

%% Add markers (optional)
% plot(x, y, 'o-', 'LineWidth', 2, 'MarkerSize', 6);

%% Labels and title
xlabel('X-axis Label');
ylabel('Y-axis Label');
title('Plot Title');

%% Grid and legend
grid on;
legend('Data Series 1', 'Location', 'best');

%% Axis limits (optional)
% xlim([xmin xmax]);
% ylim([ymin ymax]);

%% Set font size
set(gca, 'FontSize', 12, 'LineWidth', 1.5);
set(gcf, 'Color', 'w');

%% Save figure
% print('output.png', '-dpng', '-r300');
% print('output.pdf', '-dpdf');
