import os
import sys
from fetch_kaggle_dataset import process_kaggle_dataset

if __name__ == "__main__":
    print("Fetching and processing real Kaggle resume dataset...")
    process_kaggle_dataset()
