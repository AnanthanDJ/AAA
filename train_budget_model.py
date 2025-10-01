import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder
import joblib

# Load the dataset
data = pd.read_csv('mock_film_data.csv')

# Separate features and target
X = data.drop('budget', axis=1)
y = data['budget']

# One-hot encode the 'genre' column
encoder = OneHotEncoder(handle_unknown='ignore')
X_encoded = pd.get_dummies(X, columns=['genre'])

# Split the data into training and testing sets
X_train, X_test, y_train, y_test = train_test_split(X_encoded, y, test_size=0.2, random_state=42)

# Create and train the model
model = RandomForestRegressor(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

# Save the model and the columns
joblib.dump(model, 'budget_model.joblib')
joblib.dump(list(X_encoded.columns), 'model_columns.joblib')

print("Model trained and saved successfully.")
