from gensim.test.utils import common_texts as corpus, datapath
from gensim.corpora import Dictionary
from gensim.models import Word2Vec
from gensim.similarities import SoftCosineSimilarity, SparseTermSimilarityMatrix, WordEmbeddingSimilarityIndex
from gensim.models import TfidfModel
from gensim.similarities.annoy import AnnoyIndexer

if __name__ == '__main__':
    model_path = 'instruction_generator/wordnet/embeddings/gensim_jet_phrase_model.pkl'
    model = Word2Vec.load(model_path)

    dictionary = Dictionary(corpus)
    tfidf = TfidfModel(dictionary=dictionary)
    words = [word for word, count in dictionary.most_common()]
    # produce vectors for words in corpus
    word_vectors = model.wv.vectors_for_all(words, allow_inference=False)

    # use Annoy for faster word similarity lookups
    indexer = AnnoyIndexer(word_vectors, num_trees=2)
    termsim_index = WordEmbeddingSimilarityIndex(
        word_vectors, kwargs={'indexer': indexer})
    similarity_matrix = SparseTermSimilarityMatrix(
        termsim_index, dictionary, tfidf)  # compute word similarities

    tfidf_corpus = tfidf[[dictionary.doc2bow(
        document) for document in corpus]]
    docsim_index = SoftCosineSimilarity(
        tfidf_corpus, similarity_matrix, num_best=10)  # index tfidf_corpus

    query = 'graph trees computer'.split()  # make a query
    # find the ten closest documents from tfidf_corpus
    sims = docsim_index[dictionary.doc2bow(query)]
