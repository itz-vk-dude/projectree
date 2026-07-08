import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def get_ml_recommendations(user_query, df):
    # 1. Combine project features into one string for the AI to "read"
    df['combined_features'] = df['interest'] + " " + df['type'] + " " + \
        df['level'] + " " + df['language'] + " " + df['description']

    # 2. Add the user's quiz answers as the last row to compare
    combined_data = pd.concat(
        [df['combined_features'], pd.Series([user_query])], ignore_index=True)

    # 3. Turn text into Math (Vectorization)
    tfidf = TfidfVectorizer(stop_words='english')
    matrix = tfidf.fit_transform(combined_data)

    # 4. Calculate how similar each project is to the user's quiz
    # We compare the last item (user query) against all projects
    similarity_scores = cosine_similarity(matrix[-1], matrix[:-1])[0]

    # 5. Add scores to our dataframe and sort them
    df['score'] = similarity_scores
    return df.sort_values(by='score', ascending=False).head(3)
