import pandas as pd

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


table = pq.read_table('irish_planning_dataset_original_pull.parquet')

# Convert the Arrow Table to a Pandas DataFrame
df = table.to_pandas()

print(df)

#print(df['PlanningAuthority'].unique())

df.to_csv('for_inspection_original.csv')
print("Done.")