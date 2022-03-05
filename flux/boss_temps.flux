from(bucket: "actors")
    |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
    |> filter(fn: (r) => r._measurement == "boss")
    |> filter(fn: (r) => (r._field == "sp1Temp_median"))
    |> yield()