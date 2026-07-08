import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class ProjectRecommender:
    def __init__(self):
        self.vectorizer = TfidfVectorizer(stop_words='english')
        self.matrix = None
        self.df = None

    def train(self, projects_list):
        if not projects_list:
            return

        data = []
        for p in projects_list:
            data.append({
                'id': p.id,
                'title': p.title,
                'description': p.description,
                'language': p.language,
                'level': p.level,
                'content': f"{p.interest} {p.type} {p.level} {p.language} {p.description}"
            })

        self.df = pd.DataFrame(data)
        self.matrix = self.vectorizer.fit_transform(self.df['content'])
        print("✅ ML Engine: 30,000 Projects Trained.")

    def get_recommendations(self, query, top_n=24):
        if self.matrix is None:
            return []

        query_vec = self.vectorizer.transform([query])
        scores = cosine_similarity(query_vec, self.matrix)[0]

        results_df = self.df.copy()
        results_df['score'] = scores
        top_matches = results_df.sort_values(
            by='score', ascending=False).head(top_n)
        return top_matches.to_dict('records')


# Initialize a single instance to be used everywhere
recommender = ProjectRecommender()
