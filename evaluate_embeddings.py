from german_vec_pipeline.benchmarks import *
from german_vec_pipeline.embeddings import Embeddings
from german_vec_pipeline.evaluation import Evaluation
from german_vec_pipeline.resources import NDFEvaluator, SRSEvaluator
from collections import namedtuple


def main():
    umls_mapper = UMLSMapper(from_dir='E:/AML4DH-DATA/UMLS')
    Embedding = namedtuple('Embedding', 'vectors dataset algorithm preprocessing')

    # multi-term: sensible for multi token concepts
    # single-term: unsensible for multi token concepts
    # JULIE: JULIE repelacement of concepts
    # SE CUI: Subsequent Estimated CUIs with own method
    embeddings_to_benchmark = [

        # Related Work
        # Embedding(Embeddings.load_w2v_format('E:/AML4DH-DATA/claims_cuis_hs_300.txt'), "Claims", "word2vec", "UNK"),
        # Embedding(Embeddings.load_w2v_format('E:/AML4DH-DATA/DeVine_etal_200.txt'), "DeVine et al.", "word2vec", "UNK"),
        # Embedding(Embeddings.load_w2v_format('E:/AML4DH-DATA/stanford_umls_svd_300.txt'),
        #           "Stanford", "word2vec", "UNK"),
        # Embedding(Embeddings.load_w2v_format('E:/AML4DH-DATA/cui2vec_pretrained.txt'), "cui2vec", "word2vec", "UNK"),
        Embedding(Embeddings.load(path="data/German_Medical.kv"), "GerVec", "word2vec", "multi-term"),

        # # Flair
        Embedding(Embeddings.assign_concepts_to_vecs(Embeddings.load(path="data/Flair_all.kv"), umls_mapper),
                  "Ger", "Flair", "Se CUI"),

        # # GGPONC
        Embedding(Embeddings.load(path="data/no_prep_vecs_test_all.kv"), "GGPONC", "word2vec", "multi-term"),
        # Embedding(Embeddings.load(path="data/GGPONC_plain_all.kv"), "GGPONC", "word2vec", "single-term"),
        # Embedding(Embeddings.load(path="data/GGPONC_JULIE_all.kv"), "GGPONC", "word2vec", "JULIE"),
        # Embedding(Embeddings.assign_concepts_to_vecs(Embeddings.load(path="data/GGPONC_no_cui_all.kv"), umls_mapper),
        #           "GGPONC", "word2vec", "SE CUI"),
        # Embedding(Embeddings.load(path="data/GGPONC_fastText_all.kv"), "GGPONC", "fastText", "multi-term"),
        # Embedding(Embeddings.load(path="data/GGPONC_glove_all.kv"), "GGPONC", "Glove", "multi-term"),
        # # Pretrained
        # # https://devmount.github.io/GermanWordEmbeddings/
        # Embedding(Embeddings.assign_concepts_to_vecs(Embeddings.load_w2v_format('E:/german.model', binary=True),
        #                                   umls_mapper), "Wikipedia + News 2015", "word2vec", "SE CUI"),
        #
        # # News
        # Embedding(Embeddings.load(path="data/60K_news_all.kv"), "News 60K", "word2vec", "multi-term"),
        # Embedding(Embeddings.load(path="data/60K_news_plain_all.kv"), "News 60K", "word2vec", "single-term"),
        # Embedding(Embeddings.load(path="data/60K_news_JULIE_all.kv"), "News 60K", "word2vec", "JULIE"),
        # Embedding(Embeddings.assign_concepts_to_vecs(Embeddings.load(path="data/60K_news_no_cui_all.kv"), umls_mapper),
        #           "News 60K", "word2vec", "SE CUI"),
        # Embedding(Embeddings.load(path="data/60K_news_all.kv"), "News 60K", "fastText", "multi-term"),
        # Embedding(Embeddings.load(path="data/60K_news_glove_all.kv"), "News 60K", "Glove", "multi-term"),
        # Embedding(Embeddings.load(path="data/500K_news_all.kv"), "News 500K", "word2vec", "multi-term"),
        # # Embedding(Embeddings.load(path="data/3M_news_all.kv"), "News 3M", "word2vec", "multi-term"),
        #
        # # JSynCC
        Embedding(Embeddings.load(path="data/JSynCC_all.kv"), "JSynCC", "word2vec", "multi-term"),
        #
        # # PubMed
        Embedding(Embeddings.load(path="data/PubMed_all.kv"), "PubMed", "word2vec", "multi-term"),
        #
        # # German Medical Concatenation
        # Embedding(Embeddings.load(path="data/German_Medical_all.kv"), "GerVec", "word2vec", "multi-term"),
        # Embedding(Embeddings.load(path="data/German_Medical_plain_all.kv"), "GerVec", "word2vec", "single-term"),
        # Embedding(Embeddings.load(path="data/German_Medical_JULIE_all.kv"), "GerVec", "word2vec", "JULIE"),
        # Embedding(Embeddings.assign_concepts_to_vecs(
        #     Embeddings.load(path="data/German_Medical_no_cui_all.kv"), umls_mapper),
        #     "GerVec", "word2vec", "SE CUI"),
        # Embedding(Embeddings.load(path="data/German_Medical_fastText_all.kv"), "GerVec", "fastText", "multi-term"),
        # Embedding(Embeddings.load(path="data/German_Medical_fastText_plain_all.kv"), "GerVec",
        #           "fastText", "single-term"),
        # Embedding(Embeddings.load(path="data/German_Medical_fastText_JULIE_all.kv"), "GerVec",
        #           "fastText", "JULIE"),
        # Embedding(Embeddings.assign_concepts_to_vecs(Embeddings.load(path="data/German_Medical_fastText_no_cui_all.kv"),
        #                                   umls_mapper), "GerVec", "fastText", "SE CUI"),
        # Embedding(Embeddings.load(path="data/German_Medical_all.kv"), "GerVec", "Glove", "multi-term"),
        # Embedding(Embeddings.load(path="data/German_Medical_Glove_plain_all.kv"), "GerVec",
        #           "Glove", "single-term"),
        # Embedding(Embeddings.load(path="data/German_Medical_Glove_JULIE_all.kv"), "GerVec",
        #           "Glove", "JULIE"),
        # Embedding(Embeddings.assign_concepts_to_vecs(
        #     Embeddings.load(path="data/German_Medical_Glove_no_cui_all.kv"), umls_mapper),
        #     "GerVec", "Glove", "SE CUI")
    ]

    evaluators = [
        UMLSEvaluator(from_dir='E:/AML4DH-DATA/UMLS'),
        NDFEvaluator(from_dir='E:/AML4DH-DATA/NDF'),
        SRSEvaluator(from_dir="E:/AML4DH-DATA/SRS"),
        MRRELEvaluator(from_dir='E:/AML4DH-DATA/UMLS')
    ]

    benchmarks_to_use = [
        HumanAssessment,
        # CategoryBenchmark,
        # CausalityBeam,
        # NDFRTBeam,
        SemanticTypeBeam,
        AssociationBeam,
        # # SilhouetteCoefficient,
        # ConceptualSimilarityChoi,
        # MedicalRelatednessMayTreatChoi,
        # MedicalRelatednessMayPreventChoi
    ]

    evaluation = Evaluation(embeddings_to_benchmark,
                            umls_mapper,
                            evaluators,
                            benchmarks_to_use)

    # benchmark.category_benchmark("Nucleotide Sequence")
    # emb = EmbeddingSet({umls_mapper.un_umls(c, single_return=True):
    #                         Embedding(umls_mapper.un_umls(c, single_return=True), ggponc_vecs[c])
    #                     for c in ggponc_vecs.vocab})
    # emb = EmbeddingSet({c: Embedding(c, ggponc_vecs[c]) for c in ggponc_vecs.vocab})
    # emb.plot_interactive("Fibroblasten", "Fremdkörper")


if __name__ == "__main__":
    main()
