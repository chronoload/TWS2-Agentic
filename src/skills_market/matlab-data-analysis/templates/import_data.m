% MATLAB Data Import Template
% Usage: Modify filename and variable names as needed

%% Import from MAT file
data = load('data.mat');

%% Import from CSV
T = readtable('data.csv');

%% Import from Excel
T = readtable('data.xlsx', 'Sheet', 'Sheet1');

%% Import from text file
data = importdata('data.txt');

%% Access table variables
% By variable name
column1 = T.VariableName;
% By index
column2 = T{:, 1};

%% Export data
writematrix(data, 'output.csv');
writecell(T, 'output.xlsx');
save('output.mat', 'data');
