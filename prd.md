# Product Requirements Document: Add ETH Contributor Address

## Objectives

Extend the Hokusai data pipeline output to include Ethereum contributor addresses alongside their data contributions. This enhancement will enable future on-chain verification, proof-of-authorship validation, and anti-sybil protection mechanisms.

## Success Criteria

- Pipeline output JSON includes ETH wallet addresses for all contributors
- Validation ensures ETH addresses are properly formatted (0x + 40 hex characters)
- Support for both single and multiple contributor scenarios
- ETH addresses are captured during data submission process
- Schema validation includes ETH address format checking

## User Personas

**Primary Users:**
- Data Contributors: Need to provide their ETH address when submitting data
- Pipeline Operators: Must validate and process ETH addresses in output generation
- Verifiers: Will use ETH addresses for on-chain verification and proof validation

## Technical Requirements

### Data Structure Changes

For single contributors, add wallet_address field:
```json
"contributor_info": {
  "contributor_id": "contributor_xyz789",
  "wallet_address": "0xAbC123...789",
  ...
}
```

For multiple contributors, include wallet_address in contributors array:
```json
"contributors": [
  {
    "id": "xyz789", 
    "wallet_address": "0xAbC123...",
    "weight": 0.7
  },
  {
    "id": "abc456",
    "wallet_address": "0xDEf456...", 
    "weight": 0.3
  }
]
```

### Validation Requirements

- ETH address format validation (0x prefix + 40 hexadecimal characters)
- Integration with existing CLI/UI data submission flow
- Schema validation updates to include ETH address fields
- Error handling for invalid ETH addresses

### Future Considerations

- Prepare infrastructure for proof-of-authorship by capturing data hash signatures
- Log signatures alongside ETH addresses for future on-chain validation
- Consider cryptographic binding between contributor identity and ETH address

## Implementation Tasks

1. Update data submission process to capture ETH addresses
2. Add ETH address validation utilities
3. Modify pipeline output schema to include wallet_address fields
4. Update existing schema validation to handle new ETH address fields
5. Add comprehensive tests for ETH address validation and output generation
6. Update CLI tools to handle ETH address input and validation
7. Document new ETH address requirements and usage