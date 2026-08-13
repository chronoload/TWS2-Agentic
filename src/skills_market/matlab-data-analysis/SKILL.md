---
name: matlab-data-analysis
description: MATLAB programming for data analysis, statistics, and visualization
---

# MATLAB Data Analysis & Visualization Skill

## Overview
Provides MATLAB programming capabilities for importing, processing, analyzing, and visualizing data.

## When to Use
Trigger this skill when the user requests:
- MATLAB data analysis or processing
- MATLAB plotting or visualization
- MATLAB statistics or statistical analysis
- MATLAB signal processing
- Reading/writing MATLAB data files

## Core Capabilities

### 1. Data Import & Export
```matlab
% Load .mat files
data = load('filename.mat');

% Import CSV
T = readtable('data.csv');

% Import Excel
T = readtable('data.xlsx', 'Sheet', 'Sheet1');

% Export data
writematrix(data, 'output.csv');
save('output.mat', 'data');
```

### 2. Data Preprocessing
```matlab
% Handle missing values
data(cleaned,:) = rmmissing(data);
data(imputed) = fillmissing(data, 'linear');

% Normalization
data_norm = normalize(data, 'range');    % [0,1]
data_std = normalize(data, 'zscore');    % zero mean, unit variance

% Filtering (moving average)
data_smooth = smoothdata(data, 'movmean', 5);

% Outlier detection (median absolute deviation)
outliers = isoutlier(data, 'median');
```

### 3. Statistical Analysis
```matlab
% Descriptive statistics
m = mean(data);
med = median(data);
s = std(data);
v = var(data);

% Correlation
R = corrcoef(x, y);

% Linear regression
p = polyfit(x, y, 1);
y_fit = polyval(p, x);

% Hypothesis testing
[h, p] = ttest(x, y);         % t-test
[p, tbl] = anova1(data, grp); % ANOVA
```

### 4. Data Visualization
```matlab
% 2D Line plot
figure;
plot(x, y, 'LineWidth', 2);
xlabel('X-axis');
ylabel('Y-axis');
title('Title');
grid on;

% Scatter plot
scatter(x, y, 'filled');

% Bar chart
bar(categories, values);

% Histogram
histogram(data, 'Normalization', 'pdf');

% Boxplot
boxplot(data, 'Labels', {'Group1', 'Group2'});

% Heatmap
heatmap(data);

% 3D Surface
[X, Y] = meshgrid(x, y);
Z = sin(X) + cos(Y);
figure;
surf(X, Y, Z);

% Subplots
figure;
subplot(2, 2, 1); plot(x1, y1);
subplot(2, 2, 2); plot(x2, y2);
```

### 5. Signal Processing
```matlab
% FFT
Y = fft(signal);
f = (0:length(Y)-1)*(Fs/length(Y));

% Power spectrum
P = abs(Y).^2 / length(Y);

% Lowpass filter
[b, a] = butter(4, 0.3, 'low');
filtered = filtfilt(b, a, signal);

% Spectrogram
spectrogram(signal, hamming(256), 200, 256, Fs, 'yaxis');
```

## Figure Formatting Best Practices
```matlab
% Publication-quality figure settings
figure('Position', [100, 100, 800, 600]);
set(gca, 'FontSize', 12, 'LineWidth', 1.5);
set(gcf, 'Color', 'w');

% Save high-resolution
print('figure.png', '-dpng', '-r300');
print('figure.pdf', '-dpdf');
```

## Bundled Resources

### Templates
- `templates/import_data.m` - Data import templates
- `templates/plot_2d.m` - 2D plotting template
- `templates/statistical_analysis.m` - Statistics template

### Usage Example
```matlab
% Complete workflow example
T = readtable('experiment_data.csv');
data = T{:, 2:end};

% Statistics
summary_stats = [mean(data), std(data), min(data), max(data)];

% Visualization
figure;
boxplot(data, 'Labels', T.Properties.VariableNames(2:end));
title('Experimental Data Distribution');
saveas(gcf, 'boxplot_output.png');
```
