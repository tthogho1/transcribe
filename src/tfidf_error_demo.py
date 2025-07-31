"""
Simple TF-IDF error demonstration and fix
"""


# Simulate the error scenario
def demonstrate_tfidf_error():
    """Demonstrate the max_df vs min_df error"""
    print("🔍 TF-IDF Parameter Error Demonstration")
    print("=" * 50)

    # Scenario 1: Small document count with conflicting parameters
    num_docs = 3
    min_df = 2  # At least 2 documents must contain the term
    max_df = 0.5  # At most 50% of documents can contain the term

    max_df_count = int(num_docs * max_df)  # 3 * 0.5 = 1.5 -> 1

    print(f"Documents: {num_docs}")
    print(f"min_df: {min_df} (at least {min_df} documents must contain term)")
    print(f"max_df: {max_df} (at most {max_df_count} documents can contain term)")
    print()

    if min_df > max_df_count:
        print("❌ ERROR: min_df ({}) > max_df_count ({})".format(min_df, max_df_count))
        print("This causes: 'max_df corresponds to < documents than min_df'")
    else:
        print("✅ Parameters are valid")

    print()
    print("🔧 Solution Strategies:")
    print("1. Reduce min_df to 1")
    print("2. Increase max_df to 1.0")
    print("3. Dynamically adjust based on document count")
    print()

    # Show the fix
    adjusted_min_df = min(min_df, max(1, num_docs // 10))
    adjusted_max_df = max_df

    if adjusted_min_df > int(num_docs * adjusted_max_df):
        adjusted_min_df = 1
        adjusted_max_df = 1.0

    print(f"🛠️ Adjusted parameters:")
    print(f"   min_df: {adjusted_min_df}")
    print(f"   max_df: {adjusted_max_df}")
    print("✅ These parameters should work")


if __name__ == "__main__":
    demonstrate_tfidf_error()
