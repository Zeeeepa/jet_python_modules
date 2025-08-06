import spacy
import numpy as np
from span_marker import SpanMarkerModel
from sklearn.manifold import TSNE
from typing import List, Dict, Tuple

# Initialize models
nlp = spacy.load("en_core_web_sm")
model = SpanMarkerModel.from_pretrained(
    "tomaarsen/span-marker-bert-base-fewnerd-fine-super").to("mps")


def tag_entities(text: str) -> List[Dict[str, str]]:
    """
    Tags entities in the input text using SpanMarker model.

    Args:
        text (str): Input text to tag entities.

    Returns:
        List[Dict[str, str]]: List of dictionaries containing entity text and label.
    """
    doc = nlp(text)
    spans = model.predict(doc)

    entities = [
        {"text": span["text"], "label": span["label"]}
        for span in spans
    ]
    return entities


def get_embeddings_and_labels(text: str) -> Tuple[np.ndarray, List[str], List[str]]:
    """
    Extracts embeddings and labels for tokens in the input text.

    Args:
        text (str): Input text to process.

    Returns:
        Tuple[np.ndarray, List[str], List[str]]: Embeddings, token texts, and entity labels.
    """
    doc = nlp(text)
    spans = model.predict(doc)

    # Get token embeddings from the model's last hidden state
    tokens = [token.text for token in doc]
    inputs = model.tokenizer(tokens, return_tensors="pt",
                             is_split_into_words=True, padding=True)
    inputs = {k: v.to("mps") for k, v in inputs.items()}
    outputs = model.model(**inputs)
    embeddings = outputs.last_hidden_state[:, 0, :].detach(
    ).cpu().numpy()  # CLS token embeddings

    # Assign labels to tokens (entity labels or 'O' for non-entities)
    token_labels = ['O'] * len(tokens)
    for span in spans:
        start_token = span['start']
        end_token = span['end']
        for i in range(start_token, end_token):
            if i < len(token_labels):
                token_labels[i] = span['label']

    return embeddings, tokens, token_labels


def visualize_embeddings(text: str) -> Tuple[Dict, List[Dict[str, str]]]:
    """
    Creates a Chart.js scatter plot configuration for token embeddings and returns tagged entities.

    Args:
        text (str): Input text to visualize embeddings.

    Returns:
        Tuple[Dict, List[Dict[str, str]]]: Chart.js config and list of tagged entities.
    """
    embeddings, tokens, labels = get_embeddings_and_labels(text)

    # Reduce dimensionality with t-SNE
    tsne = TSNE(n_components=2, random_state=42,
                perplexity=min(5, len(embeddings)-1))
    embeddings_2d = tsne.fit_transform(embeddings)

    # Prepare Chart.js data
    unique_labels = list(set(labels))
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c',
              '#d62728', '#9467bd']  # Distinct colors
    datasets = []

    for label in unique_labels:
        indices = [i for i, l in enumerate(labels) if l == label]
        dataset = {
            'label': label,
            'data': [{'x': float(embeddings_2d[i, 0]), 'y': float(embeddings_2d[i, 1])} for i in indices],
            'backgroundColor': colors[unique_labels.index(label) % len(colors)],
            'pointRadius': 5
        }
        datasets.append(dataset)

    chart_config = {
        'type': 'scatter',
        'data': {'datasets': datasets},
        'options': {
            'scales': {
                'x': {'title': {'display': True, 'text': 't-SNE Dimension 1'}},
                'y': {'title': {'display': True, 'text': 't-SNE Dimension 2'}}
            },
            'plugins': {
                'legend': {'display': True},
                'title': {'display': True, 'text': 'Token Embeddings Visualization'},
                'tooltip': {
                    'callbacks': {
                        'label': lambda context: f"{tokens[context.dataIndex]} ({labels[context.dataIndex]})"
                    }
                }
            }
        }
    }

    entities = tag_entities(text)
    return chart_config, entities
