% MATLAB Statistical Analysis Template
% Usage: Replace data variables with your own

%% Sample data
x = randn(100, 1);
y = 2*x + randn(100, 1);

%% Descriptive Statistics
mean_val = mean(x);
median_val = median(x);
std_val = std(x);
var_val = var(x);
min_val = min(x);
max_val = max(x);

fprintf('Mean: %.4f\n', mean_val);
fprintf('Std Dev: %.4f\n', std_val);

%% Correlation Analysis
R = corrcoef(x, y);
fprintf('Correlation coefficient: %.4f\n', R(1,2));

%% Linear Regression
p = polyfit(x, y, 1);
y_fit = polyval(p, x);

fprintf('Regression: y = %.4f*x + %.4f\n', p(1), p(2));

%% Plot regression
figure;
scatter(x, y, 'filled');
hold on;
plot(x, y_fit, 'r-', 'LineWidth', 2);
xlabel('X');
ylabel('Y');
title('Linear Regression');
grid on;
legend('Data', 'Fit');

%% Hypothesis Testing (t-test)
% Test if mean differs from zero
[h, p_val] = ttest(x);
fprintf('t-test: h=%d, p=%.4f\n', h, p_val);

%% ANOVA (one-way)
% data: combined data vector, grp: grouping variable
% [p_anova, tbl] = anova1(data, grp);
